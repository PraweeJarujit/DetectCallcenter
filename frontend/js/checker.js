/*
  ตัวตรวจ (checker) — ใช้ทั้งหน้าแรกและหน้า "ตรวจ" ในแอป
  3 โหมด: เบอร์โทร (ฟรี 5 ครั้ง/วัน) · ข้อความ SMS/LINE (Premium) · ไฟล์เสียง (Premium)
  ผลตรวจแสดงเป็น "ใบผลตรวจ" ใต้ช่องกรอก พร้อมสิ่งที่ควรทำต่อ
  ต้องโหลดหลัง api.js และ ui.js
*/

const MODES = [
  { key: "phone", label: "เบอร์โทร", long: "เบอร์โทร", icon: "phone", premium: false },
  { key: "text", label: "ข้อความ", long: "ข้อความ", icon: "message", premium: true },
  { key: "audio", label: "เสียง", long: "ไฟล์เสียง", icon: "mic", premium: true },
];

let aiStatusPromise = null;
function aiStatus() {
  aiStatusPromise = aiStatusPromise || apiGet("/ai/status", { auth: false }).catch(() => ({ available: false }));
  return aiStatusPromise;
}

function pct(v) {
  return `${Math.round(v * 100)}%`;
}

function mountChecker(root, opts = {}) {
  const state = { mode: opts.mode || "phone", file: null, recorder: null, chunks: [] };
  const user = () => getCurrentUser();
  const premium = () => !!(user() && user().is_premium);

  root.classList.add("checker");
  root.innerHTML = `
    <div class="modes" role="tablist" aria-label="เลือกสิ่งที่ต้องการตรวจ">
      ${MODES.map((m) => `
        <button class="mode" role="tab" id="mode-${m.key}" aria-controls="pane-${m.key}" data-mode="${m.key}">
          ${icon(m.icon)}<span class="long">${m.long}</span><span class="short">${m.label}</span>
          ${m.premium ? `<svg class="lock" viewBox="0 0 24 24" aria-label="Premium">${ICONS.lock}</svg>` : ""}
        </button>`).join("")}
    </div>
    <div class="checker-body">
      <form id="pane-phone" role="tabpanel" aria-labelledby="mode-phone" novalidate>
        <label for="ck-phone">เบอร์ที่โทรหรือส่งข้อความมา</label>
        <div class="phone-row">
          <input class="input num" id="ck-phone" inputmode="tel" autocomplete="off" placeholder="08x-xxx-xxxx" maxlength="15">
          <button class="btn btn-primary btn-lg" type="submit">ตรวจเบอร์</button>
        </div>
        <div class="field-error" data-for="ck-phone"></div>
        <p class="hint" data-quota>ตรวจกับรายชื่อเบอร์ที่ผู้ใช้แจ้งว่าเป็นมิจฉาชีพ ใช้ฟรีวันละ 5 ครั้ง</p>
      </form>

      <form id="pane-text" role="tabpanel" aria-labelledby="mode-text" novalidate hidden>
        <div data-locked></div>
        <div data-unlocked>
          <label for="ck-text">วางข้อความที่ได้รับ</label>
          <textarea class="textarea" id="ck-text" maxlength="5000" placeholder="เช่น ข้อความ SMS ที่บอกว่าบัญชีถูกระงับ หรือแชท LINE ที่ขอให้โอนเงิน"></textarea>
          <div class="row" style="margin-top:12px">
            <div class="grow">
              <label for="ck-text-phone">เบอร์ผู้ส่ง (ถ้ามี)</label>
              <input class="input num" id="ck-text-phone" inputmode="tel" placeholder="ไม่บังคับ">
            </div>
            <button class="btn btn-primary btn-lg" type="submit">ตรวจข้อความ</button>
          </div>
          <p class="hint">AI อ่านข้อความแล้วบอกว่าเข้าข่ายหลอกลวงแค่ไหน พร้อมชี้จุดที่น่าสงสัย</p>
        </div>
      </form>

      <form id="pane-audio" role="tabpanel" aria-labelledby="mode-audio" novalidate hidden>
        <div data-locked></div>
        <div data-unlocked>
          <label class="dropzone" for="ck-file" id="ck-drop">
            ${icon("upload", "icon icon-lg")}
            <strong>เลือกไฟล์เสียง หรือลากมาวางที่นี่</strong>
            <span class="small">ไฟล์จากการอัดสาย, voice message ใน LINE ฯลฯ (mp3, m4a, wav, ogg ไม่เกิน 10 MB)</span>
          </label>
          <input type="file" id="ck-file" accept="audio/*,.m4a,.mp3,.wav,.ogg,.webm,.aac" class="sr-only">
          <div class="file-chip" id="ck-file-chip" hidden></div>
          <div class="row" style="margin-top:12px">
            <button class="btn btn-ghost" type="button" id="ck-rec">${icon("mic")}อัดเสียงจากลำโพง</button>
            <div class="grow">
              <label for="ck-audio-phone">เบอร์ที่โทรมา (ถ้ามี)</label>
              <input class="input num" id="ck-audio-phone" inputmode="tel" placeholder="ไม่บังคับ">
            </div>
            <button class="btn btn-primary btn-lg" type="submit">ตรวจไฟล์เสียง</button>
          </div>
          <p class="hint">AI ฟังลักษณะเสียงว่าเป็นเสียงคนจริง หรือเสียงที่สร้างด้วย AI / เลียนเสียงคนรู้จัก ใช้คลิปยาว 5 วินาทีขึ้นไปจะแม่นยำกว่า</p>
        </div>
      </form>
    </div>
    <div id="ck-result" aria-live="polite"></div>`;

  const $ = (sel) => root.querySelector(sel);
  const result = $("#ck-result");

  function lockedHtml(mode) {
    const what = mode === "text" ? "ตรวจข้อความด้วย AI" : "ตรวจไฟล์เสียงด้วย AI";
    const cta = user()
      ? `<a class="btn btn-primary" href="${pageUrl("account.html")}#upgrade">สมัคร Premium 59 บาท/เดือน</a>`
      : `<a class="btn btn-primary" href="${pageUrl("login.html")}?mode=register&next=account.html%23upgrade">สมัครสมาชิก</a>
         <a class="btn btn-ghost" href="${pageUrl("login.html")}">เข้าสู่ระบบ</a>`;
    return `<div class="locked">${icon("lock", "icon icon-lg")}
      <div><h3>${what} สำหรับสมาชิก Premium</h3>
      <p class="muted" style="margin-top:4px">59 บาทต่อเดือน ตรวจได้ไม่จำกัด ยกเลิกได้ทุกเมื่อ</p>
      <div class="row" style="margin-top:14px">${cta}</div></div></div>`;
  }

  function refreshLocks() {
    root.querySelectorAll("form").forEach((form) => {
      const locked = form.querySelector("[data-locked]");
      if (!locked) return;
      const isLocked = !premium();
      locked.innerHTML = isLocked ? lockedHtml(form.id.replace("pane-", "")) : "";
      form.querySelector("[data-unlocked]").hidden = isLocked;
    });
    root.querySelectorAll(".mode .lock").forEach((el) => (el.style.display = premium() ? "none" : ""));
    if (premium()) root.querySelector("[data-quota]").textContent = "ตรวจกับรายชื่อเบอร์ที่ผู้ใช้แจ้งว่าเป็นมิจฉาชีพ สมาชิก Premium ตรวจได้ไม่จำกัด";
  }

  function setMode(mode) {
    state.mode = mode;
    MODES.forEach((m) => {
      const tab = $(`#mode-${m.key}`);
      tab.setAttribute("aria-selected", String(m.key === mode));
      tab.tabIndex = m.key === mode ? 0 : -1;
      $(`#pane-${m.key}`).hidden = m.key !== mode;
    });
    result.innerHTML = "";
  }

  root.querySelectorAll(".mode").forEach((tab) => {
    tab.addEventListener("click", () => setMode(tab.dataset.mode));
    tab.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const i = MODES.findIndex((m) => m.key === state.mode);
      const next = MODES[(i + (e.key === "ArrowRight" ? 1 : MODES.length - 1)) % MODES.length].key;
      setMode(next);
      $(`#mode-${next}`).focus();
    });
  });

  /* ---------- phone ---------- */
  $("#pane-phone").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("#ck-phone");
    const err = root.querySelector('[data-for="ck-phone"]');
    const digits = input.value.replace(/[\s-]/g, "");
    err.textContent = "";
    input.classList.remove("is-invalid");
    if (!/^0\d{8,9}$/.test(digits) && !/^\d{4,5}$/.test(digits)) {
      err.textContent = "ใส่เบอร์โทรไทย 9-10 หลัก เช่น 0812345678";
      input.classList.add("is-invalid");
      input.focus();
      return;
    }
    const btn = e.submitter || $("#pane-phone button");
    try {
      const data = await withLoading(btn, () => apiPost("/detect/number", { phone_number: digits }, { redirectOn401: false }), "กำลังตรวจ...");
      renderNumber(data);
      if (data.remaining_today !== null && data.remaining_today !== undefined) {
        root.querySelector("[data-quota]").textContent = `ตรวจฟรีได้อีก ${data.remaining_today} ครั้งวันนี้`;
      }
      opts.onChecked && opts.onChecked();
    } catch (ex) {
      if (ex.code === "QUOTA_EXCEEDED") return renderQuota(ex.message);
      if (ex.status === 422 || ex.status === 400) { err.textContent = ex.message; input.classList.add("is-invalid"); return; }
      showError(ex);
    }
  });

  /* ---------- text ---------- */
  $("#pane-text").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#ck-text").value.trim();
    if (!text) { $("#ck-text").focus(); return showToast("วางข้อความที่ต้องการตรวจก่อน", 2600, "error"); }
    const phone = $("#ck-text-phone").value.replace(/[\s-]/g, "");
    const body = { text };
    if (phone) body.phone_number = phone;
    try {
      const data = await withLoading(e.submitter || $("#pane-text button[type=submit]"), () => apiPost("/detect/text", body), "AI กำลังอ่าน...");
      renderText(data, text);
      opts.onChecked && opts.onChecked();
    } catch (ex) {
      showError(ex);
    }
  });

  /* ---------- audio ---------- */
  const fileInput = $("#ck-file");
  const drop = $("#ck-drop");
  function setFile(file, label) {
    state.file = file;
    const chip = $("#ck-file-chip");
    if (!file) { chip.hidden = true; drop.hidden = false; return; }
    drop.hidden = true;
    chip.hidden = false;
    chip.innerHTML = `${icon("file")}<span class="grow">${escapeHtml(label || file.name)}</span>
      <span class="small muted num">${(file.size / 1024 / 1024).toFixed(2)} MB</span>
      <button class="btn btn-link small" type="button" data-clear>เปลี่ยนไฟล์</button>`;
    chip.querySelector("[data-clear]").addEventListener("click", () => { fileInput.value = ""; setFile(null); });
  }
  fileInput.addEventListener("change", () => fileInput.files[0] && setFile(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && setFile(e.dataTransfer.files[0]));

  const recBtn = $("#ck-rec");
  recBtn.addEventListener("click", async () => {
    if (state.recorder) { state.recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) return showToast("เบราว์เซอร์นี้อัดเสียงไม่ได้ ใช้การเลือกไฟล์แทน", 3200, "error");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      state.recorder = rec;
      state.chunks = [];
      const started = Date.now();
      rec.ondataavailable = (ev) => ev.data.size && state.chunks.push(ev.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        state.recorder = null;
        recBtn.classList.remove("recording");
        recBtn.innerHTML = `${icon("mic")}อัดเสียงจากลำโพง`;
        const type = rec.mimeType || "audio/webm";
        const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(state.chunks, { type: type.split(";")[0] });
        const secs = Math.round((Date.now() - started) / 1000);
        setFile(new File([blob], `recording.${ext}`, { type: type.split(";")[0] }), `เสียงที่อัดไว้ ${secs} วินาที`);
      };
      rec.start();
      recBtn.classList.add("recording");
      recBtn.innerHTML = `<span class="rec-dot"></span>หยุดอัด`;
      showToast("กำลังอัดเสียง เปิดลำโพงโทรศัพท์ใกล้ไมค์ แล้วกดหยุดเมื่อพอ", 3600);
    } catch (e) {
      showToast("ไม่ได้รับอนุญาตให้ใช้ไมโครโฟน", 3200, "error");
    }
  });

  $("#pane-audio").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.file) return showToast("เลือกไฟล์เสียงหรืออัดเสียงก่อน", 2600, "error");
    if (state.file.size > 10 * 1024 * 1024) return showToast("ไฟล์ใหญ่เกิน 10 MB", 3000, "error");
    const phone = $("#ck-audio-phone").value.replace(/[\s-]/g, "");
    const form = new FormData();
    form.append("file", state.file, state.file.name);
    const q = phone ? `?phone_number=${encodeURIComponent(phone)}` : "";
    try {
      const data = await withLoading(e.submitter || $("#pane-audio button[type=submit]"), () => apiRequest("POST", `/detect/audio${q}`, form, { isForm: true }), "AI กำลังฟัง...");
      renderAudio(data);
      opts.onChecked && opts.onChecked();
    } catch (ex) {
      showError(ex);
    }
  });

  /* ---------- verdict rendering ---------- */
  function slip(tone, { subject, stamp, score, scoreLabel, body = "", steps = [], actions = "", note = "" }) {
    const pin = Math.max(0, Math.min(100, score));
    result.innerHTML = `
      <section class="verdict tone-${tone}">
        <div class="verdict-top">
          <div class="verdict-subject">${subject}</div>
          <div class="stamp">${escapeHtml(stamp)}</div>
        </div>
        <div class="meter" aria-label="${escapeHtml(scoreLabel)} ${pin} จาก 100">
          <div class="meter-value num">${pin}<small> / 100 ${escapeHtml(scoreLabel)}</small></div>
          <div class="meter-track" style="margin-top:12px"><div class="meter-pin" style="left:${pin}%"></div></div>
          <div class="meter-scale"><span>ปลอดภัย</span><span>น่าสงสัย</span><span>อันตราย</span></div>
        </div>
        ${body}
        ${steps.length ? `<div class="next-steps"><h4>สิ่งที่ควรทำ</h4><ul>${steps.map((s) => `<li>${s}</li>`).join("")}</ul></div>` : ""}
        ${actions ? `<div class="verdict-actions">${actions}</div>` : ""}
        ${note ? `<p class="model-note">${note}</p>` : ""}
      </section>`;
    result.querySelector(".verdict").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
  }

  const DANGER_STEPS = [
    "วางสายหรือหยุดตอบทันที ไม่ต้องอธิบายอะไร",
    "อย่าโอนเงิน อย่าบอก OTP เลขบัตร หรือรหัสผ่าน และอย่ากดลิงก์",
    "ถ้าอ้างเป็นคนรู้จักหรือหน่วยงาน ให้โทรกลับเบอร์ทางการที่คุณรู้จักเอง",
    'ถ้าโอนเงินไปแล้ว โทร <a href="tel:1441"><strong>1441</strong></a> (ศูนย์ AOC) เพื่ออายัดบัญชีทันที',
  ];
  const reportBtn = (phone) => phone
    ? `<a class="btn btn-ghost" href="${pageUrl("numbers.html")}?report=${encodeURIComponent(phone)}">${icon("flag")}แจ้งเบอร์นี้</a>` : "";
  const callAoc = `<a class="btn btn-ink" href="tel:1441">${icon("phone")}โทร 1441</a>`;
  const alerted = (names) => names && names.length
    ? `<p class="test-banner">แจ้งผู้ติดต่อฉุกเฉินแล้ว: ${names.map(escapeHtml).join(", ")} (โหมดทดลอง ยังไม่ส่ง SMS จริง)</p>` : "";

  function renderNumber(d) {
    const known = d.report_count > 0;
    const tone = d.status === "high_risk" ? "danger" : d.status === "suspect" ? "warn" : "safe";
    const stamp = tone === "danger" ? "อันตราย" : tone === "warn" ? "น่าสงสัย" : "ไม่พบประวัติ";
    slip(tone, {
      subject: `เบอร์<strong class="num">${escapeHtml(formatPhone(d.phone_number))}</strong>`,
      stamp, score: d.risk_score, scoreLabel: "คะแนนความเสี่ยง",
      body: `<dl class="facts">
          <div class="fact"><dt>ถูกแจ้งว่าเป็นมิจฉาชีพ</dt><dd class="num">${d.report_count} ครั้ง</dd></div>
          <div class="fact"><dt>สถานะในระบบ</dt><dd>${escapeHtml(d.status_label)}</dd></div>
        </dl>`,
      steps: tone === "safe"
        ? ["ยังไม่มีใครแจ้งเบอร์นี้ แต่มิจฉาชีพเปลี่ยนเบอร์บ่อย ถ้าปลายสายขอให้โอนเงิน ขอ OTP หรืออ้างเป็นเจ้าหน้าที่ ให้วางสายทันที",
           "ได้รับข้อความหรือคลิปเสียงจากเบอร์นี้ ตรวจด้วย AI ได้ที่แท็บข้อความหรือเสียง"]
        : DANGER_STEPS,
      actions: (tone === "safe" ? "" : callAoc) + reportBtn(d.phone_number),
    });
  }

  function renderText(d, text) {
    const tone = d.level === "high" ? "danger" : d.level === "medium" ? "warn" : "safe";
    const signals = d.signals || [];
    const preview = text.length > 120 ? text.slice(0, 120) + "…" : text;
    slip(tone, {
      subject: `ข้อความ<strong style="font-size:1rem;font-weight:500">“${escapeHtml(preview)}”</strong>`,
      stamp: tone === "danger" ? "น่าจะหลอกลวง" : tone === "warn" ? "น่าสงสัย" : "ไม่พบสัญญาณอันตราย",
      score: d.risk_score, scoreLabel: "โอกาสเป็นข้อความหลอกลวง",
      body: (signals.length
        ? `<h4 style="margin-top:18px">จุดที่น่าสงสัย</h4><ul class="signals">${signals.map((s) =>
            `<li>${icon("alert")}<div>${escapeHtml(s.label)}<br><q>${escapeHtml(s.match)}</q></div></li>`).join("")}</ul>`
        : `<p class="muted" style="margin-top:16px">ไม่พบคำหรือรูปแบบที่มักใช้หลอกลวง</p>`) + alerted(d.alerted_contacts),
      steps: tone === "safe"
        ? ["ถ้าข้อความขอให้โอนเงินหรือกดลิงก์ ให้ตรวจกับแหล่งทางการก่อนเสมอ แม้ผลจะดูปลอดภัย"]
        : DANGER_STEPS,
      actions: tone === "safe" ? "" : callAoc,
      note: d.is_mock ? "ผลจำลอง: ระบบ AI ยังไม่ได้เชื่อมต่อ" : "",
    });
    aiNote("text");
  }

  function renderAudio(d) {
    const det = d.detail || {};
    const prob = det.synthetic_probability ?? d.risk_score / 100;
    const tone = d.is_synthetic_voice ? "danger" : prob >= 0.35 ? "warn" : "safe";
    const scores = det.segment_scores || [];
    const warnings = det.warnings || [];
    slip(tone, {
      subject: `ไฟล์เสียง<strong style="font-size:1rem;font-weight:500">${escapeHtml(d.filename)}</strong>`,
      stamp: tone === "danger" ? "น่าจะเป็นเสียง AI" : tone === "warn" ? "ไม่แน่ใจ ระวังไว้ก่อน" : "น่าจะเป็นเสียงคนจริง",
      score: d.risk_score, scoreLabel: "โอกาสเป็นเสียงสังเคราะห์",
      body: `<dl class="facts">
          <div class="fact"><dt>ความยาวที่วิเคราะห์</dt><dd class="num">${det.duration_seconds ?? "–"} วินาที</dd></div>
          <div class="fact"><dt>ช่วงที่ผิดปกติ</dt><dd class="num">${det.segments_flagged ?? 0} จาก ${det.segments_analyzed ?? scores.length} ช่วง</dd></div>
        </dl>
        ${scores.length > 1 ? `<p class="small muted" style="margin-top:14px">คะแนนแต่ละช่วงของเสียง (ทุก 2 วินาที)</p>
          <div class="segments" aria-hidden="true">${scores.map((s) => `<span class="${s >= 50 ? "hi" : ""}" style="height:${Math.max(8, s)}%"></span>`).join("")}</div>` : ""}
        ${warnings.map((w) => `<p class="test-banner">${escapeHtml(w)}</p>`).join("")}
        ${alerted(d.alerted_contacts)}`,
      steps: tone === "safe"
        ? ["เสียงคนจริงก็หลอกลวงได้ ถ้าถูกขอให้โอนเงินหรือบอกข้อมูลส่วนตัว ให้วางสายแล้วโทรกลับเบอร์ที่รู้จักเอง"]
        : ["มิจฉาชีพใช้ AI เลียนเสียงลูกหลานหรือคนรู้จักได้ วางสายแล้วโทรกลับเบอร์เดิมของคนนั้นที่คุณบันทึกไว้เอง",
           ...DANGER_STEPS.slice(1)],
      actions: tone === "safe" ? "" : callAoc,
      note: d.is_mock ? "ผลจำลอง: ระบบ AI ยังไม่ได้เชื่อมต่อ" : "",
    });
    aiNote("voice");
  }

  async function aiNote(kind) {
    const s = await aiStatus();
    const note = result.querySelector(".model-note");
    if (!s.available || (note && note.textContent)) return;
    const t = kind === "voice" ? s.voice_test : s.text_test;
    if (!t) return;
    const el = note || Object.assign(document.createElement("p"), { className: "model-note" });
    el.textContent = kind === "voice"
      ? `ผลจากโมเดล ${s.voice_model_version || ""} ซึ่งทดสอบกับเสียงที่ไม่เคยใช้เทรน ถูกต้อง ${pct(t.accuracy)} ผลนี้ช่วยประกอบการตัดสินใจ ไม่ใช่คำตัดสินเด็ดขาด`
      : `โมเดลข้อความทดสอบกับรูปแบบข้อความที่ไม่เคยเห็น ถูกต้อง ${pct(t.accuracy)} ผลนี้ช่วยประกอบการตัดสินใจ ไม่ใช่คำตัดสินเด็ดขาด`;
    if (!note) result.querySelector(".verdict").appendChild(el);
  }

  function renderQuota(message) {
    result.innerHTML = `<section class="verdict"><div class="locked">${icon("lock", "icon icon-lg")}<div>
      <h3>ใช้สิทธิ์ตรวจฟรีของวันนี้ครบแล้ว</h3><p class="muted" style="margin-top:4px">${escapeHtml(message)}</p>
      <div class="row" style="margin-top:14px"><a class="btn btn-primary" href="${pageUrl(user() ? "account.html" : "login.html?mode=register&next=account.html%23upgrade")}${user() ? "#upgrade" : ""}">สมัคร Premium 59 บาท/เดือน</a></div>
      </div></div></section>`;
  }

  setMode(state.mode);
  refreshLocks();
  document.addEventListener("vg:user", refreshLocks);
  return { setMode, refreshLocks };
}
