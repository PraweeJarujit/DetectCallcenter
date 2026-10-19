/*
  ส่วนประกอบหน้าตาที่ใช้ร่วมกัน: ไอคอน SVG (ไม่ใช้อิโมจิ), แถบเมนูบน + แถบเมนูล่างบนมือถือ
  ต้องโหลดหลัง api.js
*/

const ICONS = {
  logo: '<rect x="2.5" y="2.5" width="19" height="19" rx="6" fill="currentColor" stroke="none"/><path d="M7.5 10v4M10.5 7.5v9M13.5 9.5v5" stroke="#fff" stroke-width="2"/><path d="M15.8 12.2l1.4 1.4 2.3-2.6" stroke="#fff" stroke-width="2"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>',
  message: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 10.5h7M8.5 13.5h4"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
  wave: '<path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0"/>',
  upload: '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3 4v4h4M12 8v4.5l3 2"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  check: '<path d="M5 12.5 10 17.5 19.5 7"/>',
  alert: '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5v.01"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
  logout: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5 5h14l2 8v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5z"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  file: '<path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4M9.5 13v3M12 11v7M14.5 13v3"/>',
  shield: '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.8 7.5 9 4.3-1.2 7.5-4.5 7.5-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  admin: '<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
};

function icon(name, cls = "icon") {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

function brandMark() {
  return `<svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true" style="color:var(--jade)">${ICONS.logo}</svg>`;
}

const APP_NAV = [
  { href: "check.html", key: "check", label: "ตรวจ", icon: "shield" },
  { href: "live.html", key: "live", label: "ระหว่างสาย", icon: "wave" },
  { href: "history.html", key: "history", label: "ประวัติ", icon: "history" },
  { href: "numbers.html", key: "numbers", label: "เบอร์อันตราย", icon: "list" },
  { href: "account.html", key: "account", label: "บัญชี", icon: "user" },
];

/* วาดแถบเมนูบน + แถบล่างบนมือถือ ให้ทุกหน้าในแอปเหมือนกัน */
function mountShell(active) {
  const user = getCurrentUser();
  const nav = [...APP_NAV];
  if (user && user.role === "admin") nav.push({ href: "admin.html", key: "admin", label: "แอดมิน", icon: "admin" });
  const link = (n) => `<a href="${n.href}" ${n.key === active ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${n.label}</span></a>`;
  const header = document.getElementById("shell");
  header.className = "topbar";
  header.innerHTML = `
    <div class="container">
      <a class="brand" href="check.html">${brandMark()}<span>VoiceGuard</span></a>
      <nav class="nav" aria-label="เมนูหลัก">${nav.map(link).join("")}</nav>
      <div class="topbar-end">
        <a class="plan-badge" id="plan-badge" href="account.html"></a>
        <button class="btn btn-ghost btn-sm hide-mobile" data-logout>${icon("logout")}ออกจากระบบ</button>
      </div>
    </div>`;
  const tabbar = document.createElement("nav");
  tabbar.className = "tabbar";
  tabbar.setAttribute("aria-label", "เมนูหลัก");
  tabbar.innerHTML = nav.map(link).join("");
  document.body.appendChild(tabbar);
  document.body.classList.add("has-tabbar");
  renderPlanBadge(user);
  document.querySelectorAll("[data-logout]").forEach((el) => el.addEventListener("click", (e) => { e.preventDefault(); logout(); }));
  // อัปเดตสถานะสมาชิกล่าสุดจาก server (เช่นเพิ่งจ่ายเงิน หรือ Premium หมดอายุ)
  apiGet("/me").then((u) => { updateStoredUser(u); renderPlanBadge(u); document.dispatchEvent(new CustomEvent("vg:user", { detail: u })); }).catch(() => {});
}

function renderPlanBadge(user) {
  const el = document.getElementById("plan-badge");
  if (!el || !user) return;
  if (user.role === "admin") {
    el.textContent = "ผู้ดูแลระบบ";
    el.className = "plan-badge premium";
  } else if (user.is_premium) {
    el.textContent = "Premium";
    el.className = "plan-badge premium";
  } else {
    el.textContent = "ฟรี · อัปเกรด";
    el.className = "plan-badge";
  }
}

function statusTone(status) {
  return { high_risk: "danger", suspect: "warn", safe: "safe" }[status] || "safe";
}

function pill(status, label) {
  const tone = statusTone(status);
  return `<span class="pill pill-${tone}">${escapeHtml(label)}</span>`;
}

function emptyState(iconName, text, actionHtml = "") {
  return `<div class="empty">${icon(iconName)}<p>${text}</p>${actionHtml ? `<div style="margin-top:14px">${actionHtml}</div>` : ""}</div>`;
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "เมื่อสักครู่";
  if (diff < 3600) return `${Math.floor(diff / 60)} นาทีที่แล้ว`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ชั่วโมงที่แล้ว`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} วันที่แล้ว`;
  return formatDateTime(iso);
}
