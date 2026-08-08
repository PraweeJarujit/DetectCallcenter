/*
  Logic จำลองการรับสายและวิเคราะห์เสียงแบบเรียลไทม์ (หัวใจของหน้า Call Demo)
  จัดการ state 4 ขั้น: สายเรียกเข้า -> ระหว่างสนทนา (วิเคราะห์) -> แจ้งเตือนความเสี่ยง -> รายละเอียด/สรุปผล
*/

const RISK_TARGET = 87; // risk score เป้าหมายเมื่อวิเคราะห์เสร็จ (ตรงกับ mock ฝั่ง backend)
const RISK_THRESHOLD = 80; // เกินค่านี้ถือว่าความเสี่ยงสูง

// เก็บ reference ของ interval/timeout ทั้งหมด เพื่อเคลียร์ตอนกด Reset
const activeTimers = {
  riskInterval: null,
  callTimerInterval: null,
  alertTimeout: null,
};

let callSeconds = 0;

const el = {
  incoming: document.getElementById("incoming-screen"),
  incall: document.getElementById("incall-screen"),
  alertPanel: document.getElementById("alert-panel"),
  breakdownPanel: document.getElementById("breakdown-panel"),
  overlay: document.getElementById("analysis-overlay"),
  statusText: document.getElementById("analysis-status-text"),
  waveform: document.getElementById("waveform"),
  riskNum: document.getElementById("risk-score-num"),
  riskBar: document.getElementById("risk-bar-fill"),
  callTimer: document.getElementById("call-timer"),
  alertRiskScore: document.getElementById("alert-risk-score"),
  breakdownList: document.getElementById("breakdown-list"),
};

/* นาฬิกาบน status bar ของมือถือจำลอง เดินตามเวลาจริง */
function startStatusClock() {
  const clockEl = document.getElementById("sb-clock");
  if (!clockEl) return;
  function update() {
    const now = new Date();
    clockEl.textContent =
      String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
  }
  update();
  setInterval(update, 15000);
}
startStatusClock();

/* สร้างแท่งคลื่นเสียงสำหรับ waveform animation */
function buildWaveform() {
  el.waveform.innerHTML = "";
  for (let i = 0; i < 24; i++) {
    const bar = document.createElement("span");
    el.waveform.appendChild(bar);
  }
}
buildWaveform();

function formatTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function showScreen(name) {
  el.incoming.style.display = name === "incoming" ? "flex" : "none";
  el.incall.style.display = name === "incall" ? "flex" : "none";
  el.alertPanel.style.display = name === "alert" ? "flex" : "none";
  el.breakdownPanel.style.display = name === "breakdown" ? "block" : "none";
}

/* ขั้นที่ 1 -> 2: กดรับสาย เริ่มวิเคราะห์เสียงแบบเรียลไทม์ */
function acceptCall() {
  showScreen("incall");
  callSeconds = 0;
  el.callTimer.textContent = formatTime(callSeconds);
  activeTimers.callTimerInterval = setInterval(() => {
    callSeconds++;
    el.callTimer.textContent = formatTime(callSeconds);
  }, 1000);

  animateRiskScore();
}

/* animate risk score 0% -> 87% ภายในประมาณ 6 วินาที แบบสุ่มขึ้นเรื่อยๆ ให้ดูสมจริง */
function animateRiskScore() {
  let current = 0;
  el.riskNum.textContent = "0%";
  el.riskBar.style.width = "0%";
  el.overlay.classList.remove("danger");
  el.statusText.textContent = "กำลังวิเคราะห์เสียง...";

  activeTimers.riskInterval = setInterval(() => {
    current += Math.random() * 9 + 4; // เพิ่มทีละ 4-13% ต่อ tick
    if (current >= RISK_TARGET) {
      current = RISK_TARGET;
    }

    const rounded = Math.round(current);
    el.riskNum.textContent = rounded + "%";
    el.riskBar.style.width = rounded + "%";

    if (rounded >= RISK_THRESHOLD) {
      el.overlay.classList.add("danger");
      el.statusText.textContent = "ตรวจพบความเสี่ยงสูง!";
    }

    if (current >= RISK_TARGET) {
      clearInterval(activeTimers.riskInterval);
      el.alertRiskScore.textContent = RISK_TARGET;
      activeTimers.alertTimeout = setTimeout(() => {
        showScreen("alert");
      }, 900);
    }
  }, 550);
}

/* วางสายทันที -> เก็บผลลง localStorage แล้วไปหน้าสรุปผล */
function hangUpAndReport() {
  const callResult = {
    phone: "064-XXX-XX21",
    risk_score: RISK_TARGET,
    detected_at: new Date().toLocaleString("th-TH"),
  };
  localStorage.setItem("vg_last_call", JSON.stringify(callResult));
  window.location.href = "report-summary.html";
}

/* ดูรายละเอียด -> ดึงข้อมูล breakdown จาก backend แล้ว animate bar chart */
async function viewDetail() {
  showScreen("breakdown");
  el.breakdownList.innerHTML = "<p style='color:#c7cdea;font-size:14px;'>กำลังโหลดผลวิเคราะห์...</p>";

  let breakdown;
  try {
    const data = await apiGet("/calls/demo-analysis");
    breakdown = data.breakdown;
  } catch (e) {
    // fallback หาก backend ไม่ตอบ ยังคง demo ต่อได้
    breakdown = [
      { label: "ความผิดปกติของ pitch pattern", value: 92 },
      { label: "พบ artifact จากการสังเคราะห์เสียง", value: 85 },
      { label: "จังหวะการหยุดพูดผิดธรรมชาติ", value: 78 },
      { label: "ความสอดคล้องของสเปกตรัมเสียง", value: 81 },
    ];
  }

  el.breakdownList.innerHTML = breakdown.map((item, i) => `
    <div class="breakdown-item">
      <div class="label-row"><span>${item.label}</span><span>${item.value}%</span></div>
      <div class="breakdown-bar-track">
        <div class="breakdown-bar-fill" id="bd-bar-${i}" style="width:0%;"></div>
      </div>
    </div>
  `).join("");

  // หน่วงเล็กน้อยให้เบราว์เซอร์ layout ก่อน แล้วค่อยตั้งค่า width เพื่อให้ CSS transition เล่น
  // (ไม่ใช้ requestAnimationFrame เพราะโดนหยุดเมื่อแท็บอยู่ background)
  setTimeout(() => {
    breakdown.forEach((item, i) => {
      const bar = document.getElementById(`bd-bar-${i}`);
      if (bar) bar.style.width = item.value + "%";
    });
  }, 60);
}

/* รีเซ็ต demo กลับสู่สถานะเริ่มต้นเสมอ ใช้ตอน pitching ซ้ำหลายรอบ */
function resetDemo() {
  clearInterval(activeTimers.riskInterval);
  clearInterval(activeTimers.callTimerInterval);
  clearTimeout(activeTimers.alertTimeout);

  callSeconds = 0;
  el.callTimer.textContent = "00:00";
  el.riskNum.textContent = "0%";
  el.riskBar.style.width = "0%";
  el.overlay.classList.remove("danger");
  el.statusText.textContent = "กำลังวิเคราะห์เสียง...";

  showScreen("incoming");
}

document.getElementById("accept-btn").addEventListener("click", acceptCall);
document.getElementById("decline-btn").addEventListener("click", () => {
  showToast("ปฏิเสธสายเรียกเข้าแล้ว");
});
document.getElementById("hangup-btn").addEventListener("click", resetDemo);
document.getElementById("hangup-now-btn").addEventListener("click", hangUpAndReport);
document.getElementById("view-detail-btn").addEventListener("click", viewDetail);
document.getElementById("breakdown-hangup-btn").addEventListener("click", hangUpAndReport);
document.getElementById("breakdown-back-btn").addEventListener("click", () => showScreen("alert"));
document.getElementById("reset-btn").addEventListener("click", resetDemo);
