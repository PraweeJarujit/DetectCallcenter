/*
  เดโมโทรศัพท์ (pages/demo.html) — จำลองประสบการณ์แอป AwayCall บนมือถือ
  สายเรียกเข้า -> รับสาย -> เล่นเสียงจริง (audio/*.mp3) -> AI ประเมินทีละช่วง -> เตือนเต็มจอ -> สรุปผลเมื่อวางสาย

  ที่มาของผล (เลือกได้):
    auto      ส่งเสียงช่วงละ 4 วินาที ทุก 2 วินาที ไปที่ POST /api/live/chunk (โมเดลจริงบนเซิร์ฟเวอร์)
              ถ้าเซิร์ฟเวอร์ไม่ตอบ / โควตาหมด -> สลับไปใช้ผลที่บันทึกไว้ต่อทันที (ไม่ให้เดโมสะดุดตอนนำเสนอ)
    recorded  ใช้คะแนนที่โมเดลเดียวกันคำนวณไว้ใน audio/demo-calls.json
              (สร้างโดย ai-service/training/make_demo_calls.py + annotate_demo_calls.py)
  คำพูด: ใช้คำบรรยายตามจังหวะจริงในไฟล์เสียง ส่งให้ POST /api/live/text ถ้าเป็น Premium ไม่อย่างนั้นใช้ผลโมเดลข้อความที่บันทึกไว้
  ต้องโหลดหลัง api.js และ ui.js
*/

const D_SR = 16000;
const D_WIN = 4;
const D_HOP = 2;
const D_ALERT = 0.7;
const D_WARN = 0.4;
const D_MIN_CHUNKS = 3;
const D_BARS = 30;

const SCENARIOS = {
  scam: {
    file: "scam_ai", caller: "02-115-3790", sub: "ไม่ทราบชื่อ · โทรศัพท์บ้าน กรุงเทพฯ", initials: "?",
    title: "มิจฉาชีพอ้างเป็นตำรวจ", desc: "เสียงสังเคราะห์ (AI) อ้างคดีฟอกเงิน สั่งห้ามบอกใคร แล้วให้โอนเงิน", kind: "bad", icon: "alert",
  },
  real: {
    file: "real_human", caller: "081-462-0057", sub: "น้าพร · มือถือ", initials: "พ",
    title: "คนไทยจริงโทรมาคุย", desc: "เสียงคนจริงที่โมเดลไม่เคยได้ยินตอนเทรน (FLEURS)", kind: "good", icon: "user",
  },
};

const demo = {
  scenario: "scam", mode: "auto", state: "lock", server: "wait", meta: null,
  ctx: null, workletReady: false, ring: null, audio: null, src: null, analyser: null, out: null, node: null, muteGain: null,
  startedAt: 0, timer: null, raf: null,
  // ผลวิเคราะห์
  scores: [], scoreSrc: [], ema: null, textRisk: null, textSignals: [], textSrc: null, lineAt: 0, lineDone: 0, transcript: "",
  alerted: false, alertShown: false, liveFailed: false, premium: false, numberInfo: null,
  // ส่งเสียงไปตรวจสด
  buf: new Float32Array(D_WIN * D_SR), writeAt: 0, filled: 0, sinceSend: 0, acc: 0, accN: 0, phase: 0, ratio: 3,
  inFlight: false, pending: false, sent: 0, callLive: false, lastT: 0,
};

const $d = (s) => document.querySelector(s);
const cur = () => SCENARIOS[demo.scenario];
const meta = () => (demo.meta && demo.meta[cur().file]) || null;
const toneOf = (p) => (p == null ? "idle" : p >= D_ALERT ? "danger" : p >= D_WARN ? "warn" : "safe");
const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const callSeconds = () => (demo.audio ? (demo.lastT = demo.audio.currentTime) : demo.lastT || 0);

/* ---------------- หน้าจอโทรศัพท์ ---------------- */

function showScreen(name) {
  demo.state = name;
  document.querySelectorAll("[data-screen]").forEach((el) => el.classList.toggle("active", el.dataset.screen === name));
  const btn = $d("#call-btn");
  btn.disabled = name === "incoming" || name === "call";
  $d("#phone-hint").textContent = {
    lock: "เปิดเสียงลำโพงของคอมไว้ เสียงในสายเป็นไฟล์เสียงจริง",
    incoming: "กด รับสาย (หรือ Space) — AwayCall ตรวจเบอร์ให้ก่อนรับ",
    call: "AwayCall ฟังเสียงทุก 2 วินาที ดูผลที่แผงด้านขวา",
    ended: "ดูสรุปผล หรือเลือกสายอื่นแล้วโทรเข้าอีกครั้ง",
  }[name];
}

function tickClock() {
  const now = new Date();
  const hm = now.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", hour12: false });
  $d("#ph-clock").textContent = hm;
  $d("#lock-time").textContent = hm;
  $d("#lock-date").textContent = now.toLocaleDateString("th-TH", { weekday: "long", day: "numeric", month: "long" });
}

/* ---------------- เสียง ---------------- */

async function ensureAudio() {
  if (!demo.ctx) demo.ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (demo.ctx.state === "suspended") await demo.ctx.resume();
  if (!demo.workletReady && demo.ctx.audioWorklet) {
    try { await demo.ctx.audioWorklet.addModule("../js/pcm-capture.js"); demo.workletReady = true; } catch (_) { /* ใช้ผลที่บันทึกไว้ */ }
  }
  demo.ratio = demo.ctx.sampleRate / D_SR;
}

// เสียงเรียกเข้า: สองโทนสั้น ๆ ซ้ำ (สร้างด้วย WebAudio ไม่ต้องมีไฟล์)
function startRingtone() {
  const ctx = demo.ctx;
  const gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(ctx.destination);
  const notes = [880, 1108.7, 1318.5, 1108.7];
  const oscs = [];
  let stopped = false;
  const play = () => {
    if (stopped) return;
    const t0 = ctx.currentTime + 0.02;
    notes.concat(notes).forEach((f, i) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = f;
      const s = t0 + i * 0.16;
      g.gain.setValueAtTime(0, s);
      g.gain.linearRampToValueAtTime(0.18, s + 0.015);
      g.gain.exponentialRampToValueAtTime(0.001, s + 0.15);
      o.connect(g).connect(gain);
      o.start(s);
      o.stop(s + 0.16);
      oscs.push(o);
    });
    gain.gain.setValueAtTime(1, t0);
    if (navigator.vibrate) navigator.vibrate([400, 200, 400]);
  };
  play();
  const id = setInterval(play, 2600);
  demo.ring = () => { stopped = true; clearInterval(id); oscs.forEach((o) => { try { o.stop(); } catch (_) { /* ignore */ } }); gain.disconnect(); };
}

function stopRingtone() {
  if (demo.ring) { demo.ring(); demo.ring = null; }
}

function alertTone() {
  const ctx = demo.ctx;
  if (!ctx) return;
  [0, 0.22, 0.44].forEach((d) => {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = "square";
    o.frequency.value = 960;
    const s = ctx.currentTime + d;
    g.gain.setValueAtTime(0.0001, s);
    g.gain.linearRampToValueAtTime(0.08, s + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, s + 0.16);
    o.connect(g).connect(ctx.destination);
    o.start(s);
    o.stop(s + 0.18);
  });
}

/* ---------------- ส่งเสียงไปตรวจสด (แบบเดียวกับหน้า ตรวจระหว่างสาย) ---------------- */

// ตัดสินใจครั้งเดียวตอนรับสาย ไม่สลับกลับไปมาระหว่างสาย (ลำดับช่วงเสียงจะได้ตรงกัน)
function canLive() {
  return demo.mode === "auto" && demo.server === "ok" && demo.workletReady;
}
function useLive() {
  return demo.state === "call" || demo.state === "ended" ? demo.callLive && !demo.liveFailed : canLive();
}

function pushSamples(block) {
  const ratio = demo.ratio;
  for (let i = 0; i < block.length; i++) {
    demo.acc += block[i];
    demo.accN++;
    demo.phase += 1;
    if (demo.phase >= ratio) {
      demo.phase -= ratio;
      demo.buf[demo.writeAt] = demo.acc / demo.accN;
      demo.writeAt = (demo.writeAt + 1) % demo.buf.length;
      demo.acc = 0;
      demo.accN = 0;
      demo.filled = Math.min(demo.buf.length, demo.filled + 1);
      demo.sinceSend++;
    }
  }
  if (demo.filled >= demo.buf.length && demo.sinceSend >= D_HOP * D_SR) {
    demo.sinceSend = 0;
    sendWindow(demo.sent++);
  }
}

function currentWindow() {
  const n = demo.buf.length;
  const out = new Float32Array(n);
  out.set(demo.buf.subarray(demo.writeAt));
  out.set(demo.buf.subarray(0, demo.writeAt), n - demo.writeAt);
  return out;
}

function encodeWav16k(samples) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, D_SR, true); v.setUint32(28, D_SR * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

async function sendWindow(idx) {
  if (demo.state !== "call" || !useLive()) return;
  flash("chunk");
  const form = new FormData();
  form.append("file", encodeWav16k(currentWindow()), "chunk.wav");
  try {
    const r = await apiRequest("POST", "/live/chunk", form, { isForm: true, redirectOn401: false });
    if (demo.state !== "call") return;
    setScore(idx, r.synthetic_probability, "live");
  } catch (err) {
    if (demo.state !== "call") return;
    demo.liveFailed = true;
    const why = err.code === "QUOTA_EXCEEDED" ? "โควตาทดลองฟรีของวันนี้หมด" : err.status === 503 ? "บริการ AI ไม่พร้อม" : "เซิร์ฟเวอร์ไม่ตอบ";
    logEvent(`${why} → ใช้ผลที่บันทึกไว้จากโมเดลเดียวกันต่อ`, "warn");
    updateSourceTag();
    catchUpRecorded();
  }
}

/* ---------------- ผลวิเคราะห์ ---------------- */

function setScore(idx, p, src) {
  if (demo.scores[idx] != null) return;
  demo.scores[idx] = p;
  demo.scoreSrc[idx] = src;
  demo.ema = demo.ema == null ? p : demo.ema * 0.6 + p * 0.4;
  flash("voice");
  renderTrace();
  renderGauges();
  const n = demo.scores.filter((x) => x != null).length;
  if (n === 1) logEvent(`ผลเสียงช่วงแรก ${Math.round(p * 100)}/100 (${src === "live" ? "AI สด" : "ผลบันทึก"})`, toneOf(p));
  else if (toneOf(p) === "danger" && n === D_MIN_CHUNKS) logEvent(`เสียงเข้าข่ายเสียงสังเคราะห์ต่อเนื่อง ${n} ช่วง`, "danger");
  maybeAlert();
}

// คะแนนที่บันทึกไว้: ช่วงที่ i ครอบคลุมวินาที [2i, 2i+4] -> เผยเมื่อเสียงเล่นถึงวินาที 2i+4
function catchUpRecorded() {
  const m = meta();
  if (!m || useLive()) return;
  const t = callSeconds();
  m.window_scores.forEach((v, i) => {
    if (i * D_HOP + D_WIN <= t + 0.05) setScore(i, v / 100, "rec");
  });
}

function highlightText(text, signals) {
  let html = escapeHtml(text);
  for (const s of signals || []) {
    const m = escapeHtml(s.match || "");
    if (m.length >= 2 && m !== "ลิงก์") html = html.split(m).join(`<mark>${m}</mark>`);
  }
  return html;
}

function onWords(t) {
  const m = meta();
  if (!m || !m.lines) return;
  // ประโยคเริ่มพูด -> คำบรรยายบนจอ + บันทึกคำพูด
  while (demo.lineAt < m.lines.length && m.lines[demo.lineAt].start <= t) {
    const ln = m.lines[demo.lineAt];
    demo.transcript = (demo.transcript + " " + ln.text).trim();
    addTranscriptLine(demo.lineAt, ln);
    flash("words");
    demo.lineAt++;
  }
  // ประโยคพูดจบ -> ให้โมเดลข้อความประเมินคำพูดสะสม
  while (demo.lineDone < demo.lineAt && m.lines[demo.lineDone].end <= t) {
    scoreWords(demo.lineDone, m.lines[demo.lineDone]);
    demo.lineDone++;
  }
  const speaking = m.lines.find((l) => l.start <= t && t <= l.end + 0.4);
  $d("#caption").innerHTML = speaking ? highlightText(speaking.text, demo.textSignals) : "<span style=\"opacity:.5\">…</span>";
}

async function scoreWords(i, ln) {
  let risk = ln.text_risk, signals = ln.signals, src = "rec";
  if (demo.mode === "auto" && demo.premium && demo.server === "ok") {
    try {
      const r = await apiPost("/live/text", { text: demo.transcript.slice(-1500) }, { redirectOn401: false });
      risk = r.risk_score; signals = r.signals; src = "live";
    } catch (_) { /* ใช้ผลที่บันทึกไว้ */ }
  }
  if (demo.state !== "call") return;
  const before = new Set((demo.textSignals || []).map((s) => s.label));
  demo.textRisk = risk;
  demo.textSignals = signals;
  demo.textSrc = src;
  flash("text");
  const pill = document.querySelector(`[data-ln="${i}"] .pill`);
  if (pill) { pill.className = `pill pill-${toneOf(risk / 100)}`; pill.textContent = `${risk}`; }
  const row = document.querySelector(`[data-ln="${i}"] .tx`);
  if (row) row.innerHTML = highlightText(ln.text, signals);
  signals.filter((s) => !before.has(s.label)).forEach((s) => logEvent(`พบสัญญาณ: ${s.label}${s.match ? ` (“${s.match}”)` : ""}`, "warn"));
  renderGauges();
  maybeAlert();
}

function voiceScore() {
  const v = demo.scores.filter((x) => x != null);
  if (!v.length) return null;
  const top = [...v].sort((a, b) => b - a).slice(0, Math.max(1, Math.ceil(v.length / 2)));
  return top.reduce((a, b) => a + b, 0) / top.length;
}

function overall() {
  const v = demo.ema, t = demo.textRisk == null ? null : demo.textRisk / 100;
  if (v == null && t == null) return null;
  return Math.max(v ?? 0, t ?? 0);
}

function maybeAlert() {
  if (demo.alerted || demo.state !== "call") return;
  const n = demo.scores.filter((x) => x != null).length;
  const voiceHigh = demo.ema != null && demo.ema >= D_ALERT && n >= D_MIN_CHUNKS;
  const textHigh = demo.textRisk != null && demo.textRisk >= 70;
  const numberHigh = !!(demo.numberInfo && demo.numberInfo.is_blacklisted);
  if (!voiceHigh && !textHigh) return;
  demo.alerted = true;
  const reasons = [];
  if (voiceHigh) reasons.push(`เสียงปลายสายมีลักษณะของเสียงสังเคราะห์ (AI) ${Math.round(demo.ema * 100)}/100`);
  if (textHigh) {
    const labels = (demo.textSignals || []).slice(0, 3).map((s) => s.label);
    reasons.push(...(labels.length ? labels : [`คำพูดเข้าข่ายการหลอกลวง ${demo.textRisk}/100`]));
  }
  if (numberHigh) reasons.push(`เบอร์นี้ถูกแจ้งว่าเป็นมิจฉาชีพ ${demo.numberInfo.report_count} ครั้ง`);
  $d("#alert-reasons").innerHTML = reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("");
  $d("#aw-alert").classList.add("show");
  demo.alertShown = true;
  const phone = $d("#phone");
  phone.classList.remove("shake");
  void phone.offsetWidth;
  phone.classList.add("shake");
  if (navigator.vibrate) navigator.vibrate([250, 120, 250, 120, 250]);
  alertTone();
  flash("alert");
  logEvent(`AwayCall เตือนเต็มจอที่ ${mmss(callSeconds())} — ${voiceHigh && textHigh ? "ทั้งเสียงและคำพูด" : voiceHigh ? "จากเสียง" : "จากคำพูด"}`, "danger");
}

/* ---------------- แผงวิเคราะห์ ---------------- */

function flash(step) {
  const el = document.querySelector(`[data-p="${step}"]`);
  if (!el) return;
  el.classList.add("on");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("on"), 900);
}

function logEvent(text, tone = "") {
  const ul = $d("#events");
  if (ul.dataset.fresh !== "0") { ul.innerHTML = ""; ul.dataset.fresh = "0"; }
  const t = demo.state === "call" || demo.state === "ended" ? mmss(callSeconds()) : "--:--";
  ul.insertAdjacentHTML("beforeend", `<li><time>${t}</time><span class="dot ${tone}"></span><span>${escapeHtml(text)}</span></li>`);
  ul.scrollTop = ul.scrollHeight;
}

function renderTrace() {
  const vals = demo.scores.map((p, i) => [p, demo.scoreSrc[i]]).filter(([p]) => p != null).slice(-D_BARS);
  $d("#trace").innerHTML = vals.map(([p, src]) =>
    `<span class="${toneOf(p)}" style="height:${Math.max(8, Math.round(p * 100))}%" title="${Math.round(p * 100)}/100 · ${src === "live" ? "AI สด" : "ผลบันทึก"}"></span>`).join("");
}

function setGauge(id, p, word) {
  const el = $d(`#${id}`);
  el.className = `gauge ${id === "g-main" ? "g-main " : ""}tone-${toneOf(p)}`;
  $d(`#${id}-v`).innerHTML = p == null ? "–" : `${Math.round(p * 100)}<sub>/100</sub>`;
  if (word != null) $d(`#${id}-w`).textContent = word;
}

function renderGauges() {
  const o = overall();
  const word = o == null ? (demo.state === "call" ? "กำลังฟัง…" : "ยังไม่เริ่มสาย")
    : o >= D_ALERT ? "น่าจะเป็นมิจฉาชีพ" : o >= D_WARN ? "เริ่มน่าสงสัย" : "ยังไม่พบสัญญาณอันตราย";
  setGauge("g-main", o, word);
  setGauge("g-voice", demo.ema);
  setGauge("g-text", demo.textRisk == null ? null : demo.textRisk / 100);
  const live = demo.scoreSrc.filter((s) => s === "live").length, rec = demo.scoreSrc.filter((s) => s === "rec").length;
  $d("#g-voice-src").textContent = !live && !rec ? "โมเดลเสียง" : rec && !live ? "ผลบันทึกจากโมเดล" : !rec ? "AI สดจากเซิร์ฟเวอร์" : `สด ${live} · บันทึก ${rec} ช่วง`;
  $d("#g-text-src").textContent = demo.textSrc == null ? "โมเดลข้อความ" : demo.textSrc === "live" ? "AI สดจากเซิร์ฟเวอร์" : "ผลบันทึกจากโมเดล";

  // แถบ AwayCall บนจอโทรศัพท์
  const bar = $d("#aw-live");
  const t = toneOf(o);
  bar.className = `aw-live ${t === "idle" ? "" : t}`;
  $d("#aw-score").textContent = o == null ? "–" : Math.round(o * 100);
  $d("#aw-word").textContent = o == null ? "AwayCall กำลังฟัง" : t === "danger" ? "AwayCall: ระวังสายนี้" : t === "warn" ? "AwayCall: เริ่มน่าสงสัย" : "AwayCall: ฟังดูปกติ";
  const n = demo.scores.filter((x) => x != null).length;
  $d("#aw-sub").textContent = o == null ? "รอเสียงพูด 4 วินาทีแรก" : `ตรวจแล้ว ${n} ช่วง${demo.textSignals.length ? ` · ${demo.textSignals[0].label.split(" ")[0]}` : ""}`;
}

function addTranscriptLine(i, ln) {
  const box = $d("#transcript");
  if (box.querySelector(".empty-ln")) box.innerHTML = "";
  box.insertAdjacentHTML("beforeend",
    `<div class="ln" data-ln="${i}"><time>${mmss(ln.start)}</time><span class="tx">${escapeHtml(ln.text)}</span><span class="pill pill-plain">…</span></div>`);
  box.scrollTop = box.scrollHeight;
}

function updateSourceTag() {
  const tag = $d("#src-tag");
  if (demo.state === "lock") { tag.className = "src-tag"; tag.textContent = "พร้อม"; return; }
  if (useLive()) { tag.className = "src-tag live"; tag.textContent = "● AI สดจากเซิร์ฟเวอร์"; }
  else { tag.className = "src-tag rec"; tag.textContent = "ผลที่บันทึกจากโมเดลเดียวกัน"; }
}

function resetAnalysis() {
  Object.assign(demo, {
    scores: [], scoreSrc: [], ema: null, textRisk: null, textSignals: [], textSrc: null, lineAt: 0, lineDone: 0, transcript: "",
    alerted: false, alertShown: false, liveFailed: false, numberInfo: null, callLive: false, lastT: 0,
    writeAt: 0, filled: 0, sinceSend: 0, acc: 0, accN: 0, phase: 0, inFlight: false, pending: false, sent: 0,
  });
  demo.buf.fill(0);
  $d("#trace").innerHTML = "";
  $d("#transcript").innerHTML = `<div class="empty-ln">คำพูดจะขึ้นที่นี่เมื่อรับสาย</div>`;
  $d("#events").innerHTML = `<li><time>--:--</time><span class="dot"></span><span>รอสายเรียกเข้า</span></li>`;
  $d("#events").dataset.fresh = "1";
  $d("#aw-alert").classList.remove("show");
  $d("#caption").textContent = "…";
  renderGauges();
}

/* ---------------- ขั้นตอนของสาย ---------------- */

async function incomingCall() {
  if (demo.state === "incoming" || demo.state === "call") return;
  await ensureAudio();
  teardownCall();
  resetAnalysis();
  const s = cur();
  $d("#in-number").textContent = s.caller;
  $d("#in-sub").textContent = s.sub;
  $d("#in-avatar").textContent = s.initials;
  $d("#call-number").textContent = s.caller;
  const chip = $d("#in-chip");
  chip.className = "aw-chip";
  chip.querySelector("span").textContent = "AwayCall กำลังตรวจเบอร์…";
  showScreen("incoming");
  updateSourceTag();
  startRingtone();
  logEvent(`สายเรียกเข้าจาก ${s.caller}`, "brand");

  if (demo.mode === "auto" && demo.server === "ok") {
    try {
      const r = await apiPost("/detect/number", { phone_number: s.caller.replace(/-/g, "") }, { redirectOn401: false });
      demo.numberInfo = r;
      if (demo.state !== "incoming" && demo.state !== "call") return;
      chip.className = `aw-chip ${statusTone(r.status)}`;
      chip.querySelector("span").textContent = r.is_blacklisted
        ? `${r.status_label} · ถูกแจ้ง ${r.report_count} ครั้ง` : "ไม่พบในรายชื่อเบอร์อันตราย · จะฟังสายให้";
      logEvent(`ตรวจเบอร์: ${r.status_label}${r.is_blacklisted ? ` (ถูกแจ้ง ${r.report_count} ครั้ง)` : ""}`, r.is_blacklisted ? "danger" : "safe");
      return;
    } catch (_) { /* โควตาตรวจเบอร์หมด หรือออฟไลน์ */ }
  }
  setTimeout(() => {
    if (demo.state !== "incoming") return;
    chip.className = "aw-chip";
    chip.querySelector("span").textContent = "AwayCall พร้อมฟังสายนี้ให้คุณ";
  }, 900);
}

async function acceptCall() {
  if (demo.state !== "incoming") return;
  stopRingtone();
  const s = cur();
  const ctx = demo.ctx;
  const audio = new Audio(`../audio/${s.file}.mp3`);
  audio.preload = "auto";
  demo.audio = audio;
  demo.src = ctx.createMediaElementSource(audio);
  demo.analyser = ctx.createAnalyser();
  demo.analyser.fftSize = 2048;
  demo.analyser.smoothingTimeConstant = 0.82;
  demo.out = ctx.createGain();
  demo.out.gain.value = 1;
  // เสียงผ่าน analyser ก่อนออกลำโพง (analyser ที่ไม่ต่อปลายทาง Chrome อาจไม่ประมวลผล คลื่นเสียงจะนิ่ง)
  demo.src.connect(demo.analyser).connect(demo.out).connect(ctx.destination);
  if (demo.workletReady) {
    demo.node = new AudioWorkletNode(ctx, "pcm-capture");
    demo.node.port.onmessage = (e) => { if (demo.state === "call" && useLive()) pushSamples(e.data); };
    demo.muteGain = ctx.createGain();
    demo.muteGain.gain.value = 0;
    demo.src.connect(demo.node);
    demo.node.connect(demo.muteGain).connect(ctx.destination);
  }
  audio.addEventListener("ended", () => setTimeout(() => { if (demo.state === "call") endCall("remote"); }, 700));
  demo.callLive = canLive();
  showScreen("call");
  updateSourceTag();
  logEvent(useLive() ? "รับสาย · ส่งเสียงให้โมเดลบนเซิร์ฟเวอร์ตรวจทุก 2 วินาที" : "รับสาย · ใช้ผลที่โมเดลคำนวณไว้ ตามจังหวะเสียงจริง", "brand");
  flash("audio");
  try { await audio.play(); } catch (_) { showToast("เบราว์เซอร์ไม่ยอมเล่นเสียง ลองกดรับสายอีกครั้ง", 3000, "error"); }
  demo.startedAt = performance.now();
  loop();
}

function loop() {
  if (demo.state !== "call") return;
  const t = callSeconds();
  $d("#call-timer").textContent = mmss(t);
  onWords(t);
  if (!useLive()) catchUpRecorded();
  drawWave();
  demo.raf = requestAnimationFrame(loop);
}

function drawWave() {
  const c = $d("#wave");
  const g = c.getContext("2d");
  const a = demo.analyser;
  g.clearRect(0, 0, c.width, c.height);
  if (!a) return;
  // สเปกตรัมความถี่เสียงพูด (~80 Hz – 4 kHz) แบบสมมาตร อ่านง่ายกว่ารูปคลื่นดิบ
  const data = new Uint8Array(a.frequencyBinCount);
  a.getByteFrequencyData(data);
  const hz = demo.ctx.sampleRate / 2 / data.length;
  const lo = Math.max(1, Math.floor(80 / hz)), hi = Math.floor(4000 / hz);
  const half = 22, n = half * 2, w = c.width / n;
  const tone = toneOf(overall());
  const color = { danger: "255,106,87", warn: "247,173,0", safe: "24,202,168", idle: "255,255,255" }[tone];
  for (let k = 0; k < half; k++) {
    const from = lo + Math.floor((hi - lo) * Math.pow(k / half, 1.6));
    const to = Math.max(from + 1, lo + Math.floor((hi - lo) * Math.pow((k + 1) / half, 1.6)));
    let sum = 0;
    for (let j = from; j < to; j++) sum += data[j];
    const v = sum / (to - from) / 255;
    const h = Math.max(3, Math.pow(v, 1.3) * c.height);
    g.fillStyle = `rgba(${color},${0.55 + v * 0.45})`;
    for (const i of [half - 1 - k, half + k]) g.fillRect(i * w + 1, (c.height - h) / 2, w - 2.5, h);
  }
}

function teardownCall() {
  stopRingtone();
  cancelAnimationFrame(demo.raf);
  if (demo.audio) { demo.audio.pause(); demo.audio = null; }
  for (const k of ["node", "muteGain", "out", "analyser", "src"]) {
    if (demo[k]) { try { demo[k].disconnect(); } catch (_) { /* ignore */ } demo[k] = null; }
  }
}

function endCall(reason) {
  if (demo.state === "incoming" && reason === "decline") {
    teardownCall();
    logEvent("คุณปฏิเสธสาย", "");
    $d("#end-number").textContent = cur().caller;
    $d("#end-time").textContent = "ปฏิเสธสาย";
    $d("#sum-card").innerHTML = `<b>ปฏิเสธสายแล้ว</b><p style="margin-top:6px;color:var(--ink-2)">ถ้าไม่แน่ใจว่าใครโทรมา ใส่เบอร์ในหน้า ตรวจ ของ AwayCall ได้ฟรี</p>`;
    renderSumActions(false);
    showScreen("ended");
    return;
  }
  if (demo.state !== "call") return;
  const secs = callSeconds();
  if (!useLive()) catchUpRecorded();
  teardownCall();
  showScreen("ended");
  $d("#aw-alert").classList.remove("show");
  logEvent(reason === "remote" ? "ปลายสายวางสาย" : demo.alerted ? "คุณวางสายหลังได้รับคำเตือน" : "คุณวางสาย", reason === "user" && demo.alerted ? "safe" : "");
  renderSummary(secs);
  updateSourceTag();
}

function renderSummary(secs) {
  const v = voiceScore();
  const t = demo.textRisk;
  const worst = Math.max(v == null ? 0 : v, t == null ? 0 : t / 100);
  const tone = toneOf(worst);
  const n = demo.scores.filter((x) => x != null).length;
  const word = !n && t == null ? "ฟังน้อยเกินกว่าจะตัดสิน" : tone === "danger" ? "น่าจะเป็นมิจฉาชีพ" : tone === "warn" ? "น่าสงสัย ควรระวัง" : "ไม่พบสัญญาณอันตราย";
  $d("#end-number").textContent = cur().caller;
  $d("#end-time").textContent = `คุยไป ${mmss(secs)}`;
  $d("#sum-card").innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
      <span style="font-weight:600;display:flex;align-items:center;gap:6px"><svg viewBox="0 0 24 24" class="icon" style="color:var(--brand);width:18px;height:18px">${ICONS.glyph}</svg>สรุปจาก AwayCall</span>
    </div>
    <div class="tone-${tone === "idle" ? "safe" : tone}" style="margin-top:8px"><span class="stamp">${word}</span></div>
    <div class="row2">
      <div><small>เสียง AI</small><b>${v == null ? "–" : Math.round(v * 100)}</b></div>
      <div><small>คำพูดเสี่ยง</small><b>${t == null ? "–" : t}</b></div>
      <div><small>ช่วงที่ตรวจ</small><b>${n}</b></div>
      <div><small>เตือนเมื่อ</small><b>${demo.alerted ? firstAlertTime() : "–"}</b></div>
    </div>`;
  renderSumActions(tone === "danger" || tone === "warn");
  renderGauges();
  // จบสายแล้ว แสดงผลสรุปแบบเดียวกับบนโทรศัพท์ (เสียง = ค่าเฉลี่ยครึ่งบนของทุกช่วง)
  setGauge("g-main", n || t != null ? worst : null, `สรุป: ${word}`);
  setGauge("g-voice", v);
  $d("#g-voice-src").textContent = "สรุปทั้งสาย (เฉลี่ยครึ่งบน)";
}

function firstAlertTime() {
  const li = [...document.querySelectorAll("#events li")].find((x) => x.textContent.includes("เตือนเต็มจอ"));
  return li ? li.querySelector("time").textContent : "–";
}

function renderSumActions(risky) {
  const s = cur();
  const other = demo.scenario === "scam" ? "real" : "scam";
  $d("#sum-actions").innerHTML = `
    ${risky ? `<a class="p" href="numbers.html?report=${encodeURIComponent(s.caller.replace(/-/g, ""))}">แจ้งเบอร์นี้ให้คนอื่นรู้</a>` : ""}
    <button class="${risky ? "s" : "p"}" type="button" data-next="${other}">ลองอีกสาย: ${escapeHtml(SCENARIOS[other].title)}</button>
    <button class="s" type="button" data-lock>กลับหน้าจอหลัก</button>`;
  $d("#sum-actions [data-next]").addEventListener("click", (e) => { pickScenario(e.currentTarget.dataset.next); incomingCall(); });
  $d("#sum-actions [data-lock]").addEventListener("click", resetDemo);
}

function resetDemo() {
  teardownCall();
  resetAnalysis();
  showScreen("lock");
  updateSourceTag();
}

/* ---------------- ส่วนควบคุม ---------------- */

function pickScenario(key) {
  if (demo.state === "call" || demo.state === "incoming") return;
  demo.scenario = key;
  document.querySelectorAll("[data-scen]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.scen === key)));
}

function setMode(mode) {
  if (demo.state === "call") return;
  demo.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  $d("#mode-note").textContent = mode === "auto"
    ? "ส่งเสียงไปให้โมเดลจริงตรวจทีละช่วง ถ้าเซิร์ฟเวอร์ไม่ตอบ จะสลับไปใช้ผลที่โมเดลเดียวกันคำนวณไว้ล่วงหน้าให้อัตโนมัติ"
    : "ไม่ต้องต่อเซิร์ฟเวอร์ ใช้คะแนนที่โมเดลเดียวกันคำนวณจากไฟล์เสียงนี้ไว้แล้ว แสดงตามจังหวะเสียงจริง (เหมาะกับนำเสนอแบบออฟไลน์)";
  updateSourceTag();
}

async function checkServer(attempt = 1) {
  const el = $d("#srv");
  const set = (cls, text) => { demo.server = cls; el.className = `srv ${cls}`; el.querySelector("span").textContent = text; };
  if (attempt === 1) set("wait", "กำลังเช็กเซิร์ฟเวอร์ AI… (ครั้งแรกอาจใช้เวลาปลุกเครื่อง ~1 นาที)");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 70000);
  try {
    const r = await fetch(`${API_BASE}/ai/status`, { signal: ctrl.signal });
    const s = r.ok ? await r.json() : null;
    const data = s && (s.data || s);
    if (data && data.available) {
      set("ok", `เซิร์ฟเวอร์ AI พร้อม · โมเดลเสียง ${data.voice_model_version || ""}`.trim());
      try {
        const q = await apiGet("/live/quota", { redirectOn401: false });
        demo.premium = !!q.text_analysis;
        if (!q.premium && q.free_chunks_left != null) el.querySelector("span").textContent += ` · ตรวจสดฟรีเหลือ ${q.free_chunks_left} ช่วงวันนี้`;
      } catch (_) { /* ignore */ }
    } else if (attempt < 3) {
      // backend ตื่นแล้วแต่ ai-service อาจยังปลุกไม่เสร็จ (Render free plan) ลองใหม่อีกครั้ง
      set("wait", "กำลังปลุกเซิร์ฟเวอร์ AI… ระหว่างนี้เดโมใช้ผลที่บันทึกไว้ได้");
      setTimeout(() => checkServer(attempt + 1), 15000);
      return;
    } else {
      set("off", "เซิร์ฟเวอร์ AI ไม่พร้อม — ใช้ผลที่บันทึกไว้แทนอัตโนมัติ");
    }
  } catch (_) {
    set("off", "ต่อเซิร์ฟเวอร์ไม่ได้ — ใช้ผลที่บันทึกไว้แทนอัตโนมัติ");
  } finally {
    clearTimeout(timer);
    updateSourceTag();
  }
}

function mountDemo() {
  $d("#scenarios").innerHTML = Object.entries(SCENARIOS).map(([k, s], i) => `
    <button type="button" data-scen="${k}" aria-pressed="${k === demo.scenario}">
      <span class="si ${s.kind}">${icon(s.icon)}</span>
      <span><strong>${i + 1}. ${escapeHtml(s.title)}</strong><span class="d">${escapeHtml(s.caller)} · ${escapeHtml(s.desc)}</span></span>
    </button>`).join("");
  document.querySelectorAll("[data-scen]").forEach((b) => b.addEventListener("click", () => pickScenario(b.dataset.scen)));
  document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  const params = new URLSearchParams(location.search);
  if (SCENARIOS[params.get("call")]) pickScenario(params.get("call"));
  if (params.get("mode") === "recorded") setMode("recorded");

  $d("#call-btn").addEventListener("click", incomingCall);
  $d("#lock-call").addEventListener("click", incomingCall);
  $d("#reset-btn").addEventListener("click", resetDemo);
  $d("#accept-btn").addEventListener("click", acceptCall);
  $d("#decline-btn").addEventListener("click", () => endCall("decline"));
  $d("#hangup-btn").addEventListener("click", () => endCall("user"));
  $d("#alert-hangup").addEventListener("click", () => endCall("user"));
  $d("#alert-dismiss").addEventListener("click", () => { $d("#aw-alert").classList.remove("show"); logEvent("ผู้ใช้เลือกฟังต่อ (ไม่แนะนำ)", "warn"); });
  $d("#mute-btn").addEventListener("click", (e) => { e.currentTarget.classList.toggle("on"); });
  $d("#spk-btn").addEventListener("click", (e) => {
    const on = e.currentTarget.classList.toggle("on");
    if (demo.out) demo.out.gain.value = on ? 1 : 0.25;
  });
  $d("#present-btn").addEventListener("click", () => {
    const el = document.documentElement;
    if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen().catch(() => {});
    else if (document.exitFullscreen) document.exitFullscreen();
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if (e.code === "Space") {
      e.preventDefault();
      if (demo.state === "incoming") acceptCall();
      else if (demo.state === "call") endCall("user");
      else incomingCall();
    } else if (e.key === "r" || e.key === "R") resetDemo();
    else if (e.key === "1") pickScenario("scam");
    else if (e.key === "2") pickScenario("real");
  });

  fetch("../audio/demo-calls.json").then((r) => (r.ok ? r.json() : null)).then((d) => {
    demo.meta = d;
    if (d) {
      $d("#console-foot").textContent =
        `โมเดลเสียง ${d.model_version || ""} · โมเดลข้อความ ${(d.text_model && d.text_model.name) || ""} · ` +
        `ผลบันทึกคำนวณจากไฟล์เสียงเดียวกันนี้ ไม่ใช่ตัวเลขที่ตั้งเอง · เสียงมิจฉาชีพสร้างด้วย ${(d.scam_ai && d.scam_ai.voice) || "TTS"} จากบทที่เขียนใหม่`;
    }
  }).catch(() => {});

  tickClock();
  setInterval(tickClock, 15000);
  resetAnalysis();
  showScreen("lock");
  checkServer();
  window.addEventListener("beforeunload", teardownCall);
}
