/*
  ตรวจระหว่างสาย (เรียลไทม์)
  เสียงเข้า -> แปลงเป็น 16 kHz mono -> ทุก 2 วินาทีส่งเสียง 4 วินาทีล่าสุดไปที่ POST /api/live/chunk
  -> โมเดลเสียงจริงใน ai-service ตอบความน่าจะเป็นเสียงสังเคราะห์ -> เกจ + แถบเส้นเวลาขยับตามผลจริง
  คำพูด (ไมค์, Chrome) หรือคำบรรยาย (สายตัวอย่าง) -> POST /api/live/text (Premium) จับคำพูดเข้าข่ายหลอกลวง
  จบสาย -> POST /api/live/summary บันทึกประวัติ 1 แถว (ยกเว้นสายตัวอย่าง)
  ต้องโหลดหลัง api.js และ ui.js
*/

const LIVE_SR = 16000;
const WIN_S = 4;
const HOP_S = 2;
const ALERT_AT = 0.7;
const WARN_AT = 0.4;
const MIN_CHUNKS_FOR_ALERT = 3;
const MAX_BARS = 60;

const DEMO_CALLS = {
  scam: { file: "scam_ai", caller: "02-115-3790", label: "อ้างเป็นตำรวจ", desc: "สายจากมิจฉาชีพที่ใช้เสียง AI พูดแทน" },
  real: { file: "real_human", caller: "081-462-0057", label: "คนไทยจริง", desc: "เสียงคนจริงที่โมเดลไม่เคยได้ยินตอนเทรน" },
};

const live = {
  source: "demo", demo: "scam", running: false, startedAt: 0, clock: null,
  ctx: null, node: null, mediaStream: null, audioEl: null, recog: null,
  ring: new Float32Array(WIN_S * LIVE_SR), writeAt: 0, filled: 0, sinceSend: 0, acc: 0, accN: 0, phase: 0, ratio: 3,
  inFlight: false, pending: false, probs: [], ema: null, alerted: false,
  transcript: "", interim: "", textRisk: null, textSignals: [], textTimer: null, captions: [], captionAt: 0,
  quota: null, phone: null, number: null, demoMeta: null, demoMetaAll: null,
};

const $l = (sel) => document.querySelector(sel);
const isPremium = () => !!(live.quota && live.quota.premium);

/* ---------------- audio plumbing ---------------- */

function resetBuffers() {
  live.ring.fill(0);
  Object.assign(live, { writeAt: 0, filled: 0, sinceSend: 0, acc: 0, accN: 0, phase: 0, inFlight: false, pending: false,
    probs: [], ema: null, alerted: false, transcript: "", interim: "", textRisk: null, textSignals: [], captions: [], captionAt: 0 });
}

// ลด sample rate เป็น 16 kHz แบบเฉลี่ยกล่อง (พอสำหรับเสียงพูด) แล้วเขียนลง ring buffer 4 วินาที
function pushSamples(block) {
  const ratio = live.ratio;
  for (let i = 0; i < block.length; i++) {
    live.acc += block[i];
    live.accN++;
    live.phase += 1;
    if (live.phase >= ratio) {
      live.phase -= ratio;
      live.ring[live.writeAt] = live.acc / live.accN;
      live.writeAt = (live.writeAt + 1) % live.ring.length;
      live.acc = 0;
      live.accN = 0;
      live.filled = Math.min(live.ring.length, live.filled + 1);
      live.sinceSend++;
    }
  }
  if (live.filled >= live.ring.length && live.sinceSend >= HOP_S * LIVE_SR) {
    live.sinceSend = 0;
    sendWindow();
  }
}

function currentWindow() {
  const n = live.ring.length;
  const out = new Float32Array(n);
  out.set(live.ring.subarray(live.writeAt));
  out.set(live.ring.subarray(0, live.writeAt), n - live.writeAt);
  return out;
}

// ช่วงที่แทบไม่มีเสียงพูดไม่ต้องส่งไปตรวจ (โมเดลไม่มีอะไรให้ฟัง และประหยัดสิทธิ์ทดลองฟรี)
function voicedRatio(x) {
  const frame = 320;
  let voiced = 0, frames = 0;
  for (let i = 0; i + frame <= x.length; i += frame, frames++) {
    let e = 0;
    for (let j = i; j < i + frame; j++) e += x[j] * x[j];
    if (Math.sqrt(e / frame) > 0.006) voiced++;
  }
  return frames ? voiced / frames : 0;
}

function encodeWav(samples) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, LIVE_SR, true); v.setUint32(28, LIVE_SR * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

async function sendWindow() {
  if (!live.running) return;
  if (live.inFlight) { live.pending = true; return; }
  const win = currentWindow();
  if (voicedRatio(win) < 0.2) { addBar(null); return; }
  live.inFlight = true;
  const form = new FormData();
  form.append("file", encodeWav(win), "chunk.wav");
  try {
    const r = await apiRequest("POST", "/live/chunk", form, { isForm: true, redirectOn401: false });
    if (!live.running) return;
    onChunkResult(r);
  } catch (err) {
    if (!live.running) return;
    if (err.code === "QUOTA_EXCEEDED") { stopListening("quota", errorMessage(err)); return; }
    if (err.status === 503) { stopListening("ai-down", errorMessage(err)); return; }
    setStatusNote(errorMessage(err));
  } finally {
    live.inFlight = false;
    if (live.pending && live.running) { live.pending = false; sendWindow(); }
  }
}

function onChunkResult(r) {
  const p = r.synthetic_probability;
  live.probs.push(p);
  live.ema = live.ema == null ? p : live.ema * 0.6 + p * 0.4;
  if (r.free_chunks_left != null) live.quota.free_chunks_left = r.free_chunks_left;
  addBar(p);
  renderReadout();
  maybeAlert();
}

async function startAudioGraph(sourceNode, monitor) {
  const ctx = live.ctx;
  live.ratio = ctx.sampleRate / LIVE_SR;
  await ctx.audioWorklet.addModule("../js/pcm-capture.js");
  const node = new AudioWorkletNode(ctx, "pcm-capture");
  node.port.onmessage = (e) => { if (live.running) pushSamples(e.data); };
  const mute = ctx.createGain();
  mute.gain.value = 0;
  sourceNode.connect(node);
  node.connect(mute).connect(ctx.destination);   // ต้องต่อถึงปลายทาง worklet ถึงจะทำงาน
  if (monitor) sourceNode.connect(ctx.destination); // สายตัวอย่าง: ให้ผู้ใช้ได้ยินเสียงด้วย
  live.node = node;
}

/* ---------------- sources ---------------- */

async function startDemo() {
  const call = DEMO_CALLS[live.demo];
  live.ctx = new AudioContext();
  const audio = new Audio(`../audio/${call.file}.mp3`);
  audio.preload = "auto";
  live.audioEl = audio;
  const src = live.ctx.createMediaElementSource(audio);
  await startAudioGraph(src, true);
  audio.addEventListener("ended", () => setTimeout(() => stopListening("ended"), 400));
  audio.addEventListener("timeupdate", () => showCaptions(audio.currentTime, audio.duration));
  await audio.play();
}

async function startMic() {
  live.mediaStream = await navigator.mediaDevices.getUserMedia({
    // ปิดการประมวลผลของเบราว์เซอร์: ตัวลดเสียงรบกวนทำให้ลักษณะเสียงเปลี่ยน โมเดลจะฟังผิด
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
  });
  live.ctx = new AudioContext();
  await startAudioGraph(live.ctx.createMediaStreamSource(live.mediaStream), false);
  startSpeechRecognition();
}

async function startSystem() {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true, systemAudio: "include" });
  if (!stream.getAudioTracks().length) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error("ไม่ได้รับเสียงจากหน้าจอที่แชร์ ตอนเลือกหน้าจอให้ติ๊ก \"แชร์เสียงของระบบ\" (Share system audio) ด้วย");
  }
  live.mediaStream = stream;
  stream.getVideoTracks().forEach((t) => t.addEventListener("ended", () => stopListening("ended")));
  live.ctx = new AudioContext();
  await startAudioGraph(live.ctx.createMediaStreamSource(new MediaStream(stream.getAudioTracks())), false);
}

/* ---------------- words: speech recognition / captions -> text model ---------------- */

function startSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { setTranscriptNote("เบราว์เซอร์นี้ถอดคำพูดไม่ได้ (ใช้ Chrome หรือ Edge) — AI ยังฟังเสียงได้ตามปกติ"); return; }
  const recog = new SR();
  recog.lang = "th-TH";
  recog.continuous = true;
  recog.interimResults = true;
  recog.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) addWords(t); else interim += t;
    }
    live.interim = interim;
    renderTranscript();
  };
  recog.onerror = (e) => { if (e.error === "not-allowed") setTranscriptNote("ไม่ได้รับอนุญาตให้ถอดคำพูด"); };
  recog.onend = () => { if (live.running && live.recog === recog) { try { recog.start(); } catch (_) { /* ignore */ } } };
  live.recog = recog;
  try { recog.start(); } catch (_) { /* ignore */ }
}

function prepareCaptions(meta, duration) {
  const lines = (meta && meta.script) || [];
  const total = lines.reduce((n, l) => n + l.length, 0) || 1;
  let t = 0;
  live.captions = lines.map((text) => {
    const at = t;
    t += (text.length / total) * duration;
    return { at, text };
  });
}

function showCaptions(now, duration) {
  if (!live.captions.length && live.demoMeta && duration) prepareCaptions(live.demoMeta, duration);
  while (live.captionAt < live.captions.length && live.captions[live.captionAt].at <= now) {
    addWords(live.captions[live.captionAt].text);
    live.captionAt++;
  }
}

function addWords(text) {
  text = text.trim();
  if (!text) return;
  live.transcript = (live.transcript + " " + text).trim();
  renderTranscript();
  if (!isPremium()) return;
  clearTimeout(live.textTimer);
  live.textTimer = setTimeout(analyzeWords, 700);
}

async function analyzeWords() {
  if (!live.transcript) return;
  try {
    const r = await apiPost("/live/text", { text: live.transcript.slice(-1500) }, { redirectOn401: false });
    live.textRisk = r.risk_score;
    live.textSignals = r.signals;
    renderTranscript();
    renderReadout();
    maybeAlert();
  } catch (err) {
    setTranscriptNote(errorMessage(err));
  }
}

/* ---------------- start / stop ---------------- */

async function startListening() {
  if (live.running) return;
  if (live.demoMetaAll) live.demoMeta = live.demoMetaAll[DEMO_CALLS[live.demo].file];
  const phoneRaw = ($l("#lv-phone") && $l("#lv-phone").value.replace(/[\s-]/g, "")) || "";
  live.phone = live.source === "demo" ? null : (/^0\d{8,9}$/.test(phoneRaw) ? phoneRaw : null);
  if (phoneRaw && !live.phone && live.source !== "demo") { showToast("รูปแบบเบอร์ไม่ถูกต้อง เว้นว่างได้ถ้าไม่ทราบเบอร์", 2800, "error"); return; }
  resetBuffers();
  live.running = true;
  live.startedAt = Date.now();
  renderMonitor();
  try {
    if (live.source === "demo") await startDemo();
    else if (live.source === "mic") await startMic();
    else await startSystem();
  } catch (err) {
    live.running = false;
    teardown();
    renderIdle();
    const denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
    showToast(denied ? "ไม่ได้รับอนุญาตให้ใช้ไมโครโฟนหรือแชร์หน้าจอ" : (err.message || "เริ่มฟังไม่ได้"), 4200, "error");
    return;
  }
  live.clock = setInterval(renderStatus, 1000);
  if (live.phone) checkNumber(live.phone);
}

function teardown() {
  clearInterval(live.clock);
  clearTimeout(live.textTimer);
  if (live.recog) { const r = live.recog; live.recog = null; try { r.stop(); } catch (_) { /* ignore */ } }
  if (live.audioEl) { live.audioEl.pause(); live.audioEl = null; }
  if (live.mediaStream) { live.mediaStream.getTracks().forEach((t) => t.stop()); live.mediaStream = null; }
  if (live.node) { live.node.port.onmessage = null; live.node.disconnect(); live.node = null; }
  if (live.ctx) { live.ctx.close().catch(() => {}); live.ctx = null; }
}

function voiceScore() {
  // ค่าเฉลี่ยครึ่งบนของทุกช่วง (สูตรเดียวกับการตรวจไฟล์เสียง) — แค่บางช่วงเป็นเสียง AI ก็ยังจับได้
  if (!live.probs.length) return null;
  const top = [...live.probs].sort((a, b) => b - a).slice(0, Math.max(1, Math.ceil(live.probs.length / 2)));
  return top.reduce((a, b) => a + b, 0) / top.length;
}

async function stopListening(reason = "user", message = "") {
  if (!live.running) return;
  live.running = false;
  teardown();
  const seconds = Math.round((Date.now() - live.startedAt) / 1000);
  const v = voiceScore();
  const summary = {
    voice: v == null ? null : Math.round(v * 100), text: live.textRisk, seconds, chunks: live.probs.length,
    reason, message, alerted: [],
  };
  if (live.source !== "demo" && live.probs.length) {
    try {
      const r = await apiPost("/live/summary", {
        phone_number: live.phone, duration_seconds: seconds, voice_risk: summary.voice ?? 0,
        text_risk: live.textRisk, chunks_analyzed: live.probs.length,
      }, { redirectOn401: false });
      summary.alerted = r.alerted_contacts || [];
      summary.logged = true;
    } catch (_) { /* บันทึกไม่ได้ไม่เป็นไร ผลยังแสดงได้ */ }
  }
  renderSummary(summary);
  refreshQuota();
}

async function checkNumber(phone) {
  try {
    live.number = await apiPost("/detect/number", { phone_number: phone }, { redirectOn401: false });
    renderStatus();
    if (live.number.is_blacklisted) maybeAlert(true);
  } catch (_) { /* โควตาตรวจเบอร์หมดก็ฟังเสียงต่อได้ */ }
}

/* ---------------- rendering ---------------- */

function tone(p) {
  if (p == null) return "idle";
  return p >= ALERT_AT ? "danger" : p >= WARN_AT ? "warn" : "safe";
}

function verdictWord(p) {
  if (p == null) return live.probs.length ? "กำลังฟัง" : "รอเสียงพูด";
  return p >= ALERT_AT ? "น่าจะเป็นเสียง AI" : p >= WARN_AT ? "เริ่มน่าสงสัย" : "ฟังดูเป็นคนจริง";
}

function fmtTime(s) {
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function renderStatus() {
  const el = $l("#lv-status");
  if (!el) return;
  const secs = Math.round((Date.now() - live.startedAt) / 1000);
  const q = live.quota;
  const free = q && !q.premium && q.free_chunks_left != null ? ` · ทดลองฟรีเหลือ ~${q.free_chunks_left * HOP_S} วินาที` : "";
  const num = live.number
    ? ` · เบอร์ ${escapeHtml(formatPhone(live.number.phone_number))}: ${escapeHtml(live.number.status_label)}` : "";
  el.innerHTML = `<span class="live-dot" aria-hidden="true"></span><span>กำลังฟัง <b class="num">${fmtTime(secs)}</b></span>
    <span class="muted">ตรวจแล้ว ${live.probs.length} ช่วง${free}${num}</span>`;
}

function setStatusNote(text) {
  const el = $l("#lv-note");
  if (el) el.textContent = text;
}

function renderReadout() {
  const el = $l("#lv-readout");
  if (!el) return;
  const p = live.ema;
  el.className = `readout tone-${tone(p)}`;
  el.innerHTML = `
    <div class="readout-word">${verdictWord(p)}</div>
    <div class="readout-num num">${p == null ? "–" : Math.round(p * 100)}<small>/100</small></div>
    <div class="readout-sub">โอกาสที่เป็นเสียงสังเคราะห์ (เฉลี่ยช่วงล่าสุด)${live.textRisk != null ? ` · คำพูดเข้าข่ายหลอกลวง ${live.textRisk}/100` : ""}</div>`;
}

function addBar(p) {
  const strip = $l("#lv-trace");
  if (!strip) return;
  const bar = document.createElement("span");
  if (p == null) {
    bar.className = "quiet";
    bar.title = "ช่วงเงียบ ไม่ได้ส่งตรวจ";
  } else {
    bar.className = tone(p);
    bar.style.height = `${Math.max(8, Math.round(p * 100))}%`;
    bar.title = `${Math.round(p * 100)}/100`;
  }
  strip.appendChild(bar);
  while (strip.children.length > MAX_BARS) strip.firstChild.remove();
  renderStatus();
}

function highlight(text, signals) {
  let html = escapeHtml(text);
  for (const s of signals || []) {
    const m = escapeHtml(s.match || "");
    if (m.length >= 2 && m !== "ลิงก์") html = html.split(m).join(`<mark>${m}</mark>`);
  }
  return html;
}

function setTranscriptNote(text) {
  const el = $l("#lv-words-note");
  if (el) el.textContent = text;
}

function renderTranscript() {
  const el = $l("#lv-words");
  if (!el) return;
  const words = live.transcript || live.interim
    ? `${highlight(live.transcript, live.textSignals)} <span class="interim">${escapeHtml(live.interim)}</span>`
    : `<span class="muted">${live.source === "system" ? "โหมดเสียงจากคอมถอดคำพูดไม่ได้ AI ฟังเฉพาะเสียง" : "คำพูดที่ได้ยินจะขึ้นที่นี่"}</span>`;
  el.innerHTML = words;
  el.scrollTop = el.scrollHeight;
  const sig = $l("#lv-signals");
  if (sig) {
    sig.innerHTML = (live.textSignals || []).map((s) => `<li>${icon("alert")}<span>${escapeHtml(s.label)}</span></li>`).join("");
  }
}

function maybeAlert(fromNumber = false) {
  if (live.alerted) return;
  const voiceHigh = live.ema != null && live.ema >= ALERT_AT && live.probs.length >= MIN_CHUNKS_FOR_ALERT;
  const textHigh = live.textRisk != null && live.textRisk >= 70;
  if (!voiceHigh && !textHigh && !fromNumber) return;
  live.alerted = true;
  const reasons = [];
  if (voiceHigh) reasons.push("เสียงปลายสายมีลักษณะของเสียงสังเคราะห์ (AI)");
  if (textHigh) reasons.push("คำพูดเข้าข่ายการหลอกลวง เช่น อ้างเจ้าหน้าที่ ขอให้โอนเงิน");
  if (fromNumber) reasons.push("เบอร์นี้อยู่ในรายชื่อเบอร์ที่ถูกแจ้งว่าเป็นมิจฉาชีพ");
  const el = $l("#lv-alert");
  el.hidden = false;
  el.innerHTML = `
    <div class="alert-head">${icon("alert", "icon icon-lg")}<strong>ระวัง สายนี้น่าจะเป็นมิจฉาชีพ</strong></div>
    <ul>${reasons.map((r) => `<li>${r}</li>`).join("")}</ul>
    <p>อย่าโอนเงิน อย่าบอกรหัส OTP และอย่าติดตั้งแอปตามที่ปลายสายบอก</p>
    <div class="alert-actions">
      <button class="btn btn-danger-solid" type="button" data-hangup>${icon("close")}วางสายแล้วหยุดฟัง</button>
      <a class="btn btn-ghost" href="tel:1441">${icon("phone")}โทร 1441</a>
    </div>`;
  el.querySelector("[data-hangup]").addEventListener("click", () => stopListening("user"));
  if (navigator.vibrate) navigator.vibrate([250, 120, 250]);
}

function renderMonitor() {
  const body = $l("#lv-body");
  const demo = live.source === "demo" ? DEMO_CALLS[live.demo] : null;
  body.innerHTML = `
    <div class="monitor">
      <div class="monitor-top">
        <div class="live-status" id="lv-status"></div>
        <button class="btn btn-ink" type="button" id="lv-stop">${icon("stop")}${demo ? "วางสาย" : "หยุดฟัง"}</button>
      </div>
      ${demo ? `<div class="caller small muted">สายตัวอย่าง: ${escapeHtml(demo.caller)} · ${escapeHtml(demo.desc)}</div>` : ""}
      <div class="alert-banner" id="lv-alert" hidden role="alert"></div>
      <div class="readout tone-idle" id="lv-readout"></div>
      <div class="trace-wrap">
        <div class="trace" id="lv-trace" aria-label="ผลตรวจทีละ 2 วินาที"></div>
        <div class="trace-scale small"><span>ช่วงก่อนหน้า</span><span>ล่าสุด</span></div>
      </div>
      <div class="words">
        <div class="words-head"><h3>คำพูดในสาย</h3>${isPremium() ? "" : `<a class="small" href="account.html#upgrade">Premium ให้ AI อ่านคำพูดด้วย</a>`}</div>
        <div class="words-box" id="lv-words" aria-live="polite"></div>
        <ul class="word-signals" id="lv-signals"></ul>
        <p class="small muted" id="lv-words-note"></p>
      </div>
      <p class="small muted" id="lv-note"></p>
    </div>`;
  $l("#lv-stop").addEventListener("click", () => stopListening("user"));
  renderStatus();
  renderReadout();
  renderTranscript();
}

function renderSummary(s) {
  const v = s.voice;
  const worst = Math.max(v ?? 0, s.text ?? 0);
  const t = s.chunks ? tone(worst / 100) : "idle";
  const word = !s.chunks ? "ยังไม่ได้ยินเสียงพูดพอจะตัดสิน" : t === "danger" ? "น่าจะเป็นมิจฉาชีพ" : t === "warn" ? "น่าสงสัย ควรระวัง" : "ไม่พบสัญญาณอันตราย";
  const steps = t === "danger"
    ? ["วางสาย อย่าโอนเงินหรือให้ข้อมูลใด ๆ", "ถ้าโอนไปแล้ว โทร 1441 เพื่ออายัดบัญชีทันที", "โทรกลับหาหน่วยงาน/คนที่ถูกอ้างถึง ด้วยเบอร์ที่คุณหาเอง"]
    : t === "warn"
      ? ["อย่าเพิ่งทำตามที่ปลายสายขอ", "ถามข้อมูลที่คนจริงเท่านั้นจะรู้ หรือวางสายแล้วโทรกลับเอง"]
      : ["ยังควรระวังถ้ามีการขอเงิน รหัส OTP หรือให้ติดตั้งแอป"];
  const reasonNote = {
    quota: s.message, "ai-down": s.message || "บริการ AI ไม่พร้อมชั่วคราว ลองใหม่อีกครั้ง",
  }[s.reason];
  const isDemo = live.source === "demo";
  $l("#lv-body").innerHTML = `
    <div class="verdict tone-${t === "idle" ? "safe" : t}" style="border-top:none">
      <div class="verdict-top">
        <div class="verdict-subject">${isDemo ? "สายตัวอย่าง" : "สรุปสายนี้"}<strong>${live.phone ? escapeHtml(formatPhone(live.phone)) : `ฟังไป ${fmtTime(s.seconds)}`}</strong></div>
        <span class="stamp">${word}</span>
      </div>
      ${reasonNote ? `<div class="form-error" style="margin-top:14px">${escapeHtml(reasonNote)}${s.reason === "quota" ? ` <a href="account.html#upgrade">สมัคร Premium</a>` : ""}</div>` : ""}
      <dl class="facts">
        <div class="fact"><dt>เสียงสังเคราะห์</dt><dd class="num">${v == null ? "–" : `${v}/100`}</dd></div>
        <div class="fact"><dt>คำพูดเข้าข่ายหลอกลวง</dt><dd class="num">${s.text == null ? (isPremium() ? "–" : "เฉพาะ Premium") : `${s.text}/100`}</dd></div>
        <div class="fact"><dt>ช่วงเสียงที่ตรวจ</dt><dd class="num">${s.chunks} ช่วง (${fmtTime(s.seconds)})</dd></div>
      </dl>
      <div class="trace trace-static">${live.probs.map((p) => `<span class="${tone(p)}" style="height:${Math.max(8, Math.round(p * 100))}%"></span>`).join("")}</div>
      ${s.alerted.length ? `<p style="margin-top:14px">${icon("check")} แจ้ง ${s.alerted.map(escapeHtml).join(", ")} แล้ว (โหมดทดลอง ยังไม่ส่ง SMS จริง)</p>` : ""}
      <div class="next-steps"><h4>ควรทำอะไรต่อ</h4><ul>${steps.map((x) => `<li>${x}</li>`).join("")}</ul></div>
      <div class="verdict-actions">
        <button class="btn btn-primary" type="button" id="lv-again">${isDemo ? "ลองสายตัวอย่างอีกสาย" : "ฟังสายใหม่"}</button>
        ${live.phone && t !== "safe" ? `<a class="btn btn-ghost" href="numbers.html?report=${encodeURIComponent(live.phone)}">${icon("flag")}แจ้งเบอร์นี้</a>` : ""}
        ${s.logged ? `<a class="btn btn-ghost" href="history.html">ดูในประวัติ</a>` : ""}
      </div>
      ${isDemo ? `<p class="model-note">ผลข้างบนคำนวณจริงจากโมเดล ${escapeHtml((live.demoMeta && live.demoMeta.model_version) || "")} ทีละช่วง 4 วินาที ไม่ใช่ผลที่ตั้งไว้ล่วงหน้า</p>` : ""}
    </div>`;
  $l("#lv-again").addEventListener("click", () => {
    if (isDemo) live.demo = live.demo === "scam" ? "real" : "scam";
    renderIdle();
  });
}

/* ---------------- idle screen: choose source ---------------- */

const SOURCES = [
  { key: "demo", icon: "phone", label: "สายตัวอย่าง", short: "ตัวอย่าง" },
  { key: "mic", icon: "mic", label: "เปิดลำโพงให้ฟัง", short: "ลำโพง" },
  { key: "system", icon: "wave", label: "เสียงจากคอม", short: "คอม" },
];

function renderIdle() {
  document.querySelectorAll("[data-source]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.source === live.source)));
  const body = $l("#lv-body");
  const freeNote = live.quota && !live.quota.premium
    ? `<p class="hint">ทดลองฟรีวันนี้เหลือราว ${live.quota.free_seconds_left} วินาที · <a href="account.html#upgrade">Premium ฟังได้ไม่จำกัดทุกสาย</a></p>` : "";
  if (live.source === "demo") {
    body.innerHTML = `
      <p class="muted">ลองดู AI ฟังสายจริง ๆ ทีละช่วง เลือกสายที่ต้องการแล้วกดรับสาย (เปิดเสียงลำโพงด้วย)</p>
      <div class="incoming-grid">
        ${Object.entries(DEMO_CALLS).map(([k, c]) => `
          <div class="incoming ${k === live.demo ? "is-picked" : ""}">
            <div class="small incoming-label">สายเรียกเข้า</div>
            <div class="incoming-num num">${escapeHtml(c.caller)}</div>
            <div class="small">${escapeHtml(c.desc)}</div>
            <button class="btn btn-accept" type="button" data-demo="${k}">${icon("phone")}รับสาย</button>
          </div>`).join("")}
      </div>${freeNote}`;
    body.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => { live.demo = b.dataset.demo; startListening(); }));
    return;
  }
  const mic = live.source === "mic";
  const canSystem = !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) && !/Android|iPhone|iPad/i.test(navigator.userAgent);
  body.innerHTML = `
    <ol class="how-to">
      ${mic
        ? `<li>รับสายแล้ว<strong>เปิดลำโพง</strong> วางโทรศัพท์ใกล้คอมหรือมือถือเครื่องที่เปิดหน้านี้</li>
           <li>กดเริ่มฟัง แล้วอนุญาตให้ใช้ไมโครโฟน</li>
           <li>คุยตามปกติ ถ้าเสียงหรือคำพูดน่าสงสัย จะขึ้นเตือนทันที${isPremium() ? "" : " (Premium ให้ AI อ่านคำพูดด้วย)"}</li>`
        : `<li>ใช้กับสายจาก LINE / Messenger / Zoom บนคอมพิวเตอร์ (Chrome หรือ Edge บน Windows)</li>
           <li>กดเริ่มฟัง เลือกหน้าจอทั้งหมด แล้ว<strong>ติ๊ก "แชร์เสียงของระบบ"</strong></li>
           <li>AI จะฟังเสียงปลายสายจากลำโพงของคอมโดยตรง</li>`}
    </ol>
    ${!mic && !canSystem ? `<div class="form-error">อุปกรณ์นี้แชร์เสียงระบบไม่ได้ ใช้โหมด "เปิดลำโพงให้ฟัง" แทน</div>` : `
    <div class="row" style="margin-top:16px">
      <div class="grow"><label for="lv-phone">เบอร์ที่โทรมา (ถ้ามี)</label>
        <input class="input num" id="lv-phone" inputmode="tel" placeholder="ไม่บังคับ ใส่แล้วจะตรวจกับรายชื่อเบอร์อันตรายด้วย"></div>
      <button class="btn btn-primary btn-lg" type="button" id="lv-start">${icon(mic ? "mic" : "wave")}เริ่มฟัง</button>
    </div>`}
    ${freeNote}
    <p class="hint">ไม่เก็บเสียงหรือคำพูดของคุณ เก็บเฉพาะผลตรวจตอนจบสาย</p>`;
  const start = $l("#lv-start");
  if (start) start.addEventListener("click", startListening);
}

async function refreshQuota() {
  try { live.quota = await apiGet("/live/quota", { redirectOn401: false }); } catch (_) { live.quota = live.quota || null; }
  if (!live.running && $l("#lv-body") && !$l("#lv-body .verdict")) renderIdle();
}

function mountLive() {
  const params = new URLSearchParams(location.search);
  if (DEMO_CALLS[params.get("demo")]) { live.source = "demo"; live.demo = params.get("demo"); }
  if (["mic", "system"].includes(params.get("source"))) live.source = params.get("source");
  const tabs = $l("#lv-sources");
  tabs.innerHTML = SOURCES.map((s) => `
    <button class="mode" role="tab" data-source="${s.key}" aria-selected="${s.key === live.source}">${icon(s.icon)}<span class="long">${s.label}</span><span class="short">${s.short}</span></button>`).join("");
  tabs.querySelectorAll("[data-source]").forEach((b) => b.addEventListener("click", () => {
    if (live.running) return;
    live.source = b.dataset.source;
    renderIdle();
  }));
  fetch("../audio/demo-calls.json").then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (!d) return;
    live.demoMetaAll = d;
    live.demoMeta = d[DEMO_CALLS[live.demo].file];
  }).catch(() => {});
  renderIdle();
  refreshQuota();
  window.addEventListener("beforeunload", () => teardown());
}
