/*
  ส่วนประกอบหน้าตาที่ใช้ร่วมกัน: ไอคอน SVG (ไม่ใช้อิโมจิ), แถบเมนูบน (มี mega menu) + เมนูมือถือ,
  แถบเมนูล่างบนมือถือในหน้าแอป และ footer
  ต้องโหลดหลัง api.js
*/

const APP_NAME = "AwayCall";

const ICONS = {
  // โลโก้ AwayCall: หูโทรศัพท์ + ลูกศรส่งสายมิจฉาชีพ "ออกไป"
  logo: '<rect x="1.5" y="1.5" width="21" height="21" rx="6.5" fill="currentColor" stroke="none"/><g transform="translate(3.9 6.1) scale(.56)"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" fill="#fff" stroke="none"/></g><path d="M13.6 10.4l4.6-4.6M14.6 5.6h3.8v3.8" stroke="#fff" stroke-width="1.8"/>',
  glyph: '<g transform="translate(1.6 4.4) scale(.7)"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" fill="currentColor" stroke="none"/></g><path d="M13.4 10.6l5.8-5.8M14.6 4.6h4.8v4.8" stroke-width="2.2"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chev: '<path d="M6 9l6 6 6-6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  play: '<path d="M7 5v14l12-7z" fill="currentColor"/>',
  speaker: '<path d="M4 9.5v5h3.5L12 18V6L7.5 9.5z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
  mute: '<path d="M4 9.5v5h3.5L12 18V6L7.5 9.5z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
  keypad: '<circle cx="6" cy="5" r="1.3"/><circle cx="12" cy="5" r="1.3"/><circle cx="18" cy="5" r="1.3"/><circle cx="6" cy="11" r="1.3"/><circle cx="12" cy="11" r="1.3"/><circle cx="18" cy="11" r="1.3"/><circle cx="6" cy="17" r="1.3"/><circle cx="12" cy="17" r="1.3"/><circle cx="18" cy="17" r="1.3"/>',
  micoff: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M4 4l16 16"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14a6.5 6.5 0 0 1 3.5 6"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="M16 10.5 21 8v8l-5-2.5"/>',
  bell: '<path d="M6 10a6 6 0 0 1 12 0v4l1.8 3H4.2L6 14z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3.5 7l8.5 6 8.5-6"/>',
  presentation: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8M8 12l3-3 2 2 3-3"/>',
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
  return `<svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">${ICONS.logo}</svg>`;
}

function brandHtml() {
  return `${brandMark()}<span>Away<b>Call</b></span>`;
}

/* ---------------- เมนูเว็บ (หน้าแรก / หน้าที่เปิดได้โดยไม่ login) ---------------- */

const home = (hash = "") => pageUrl("index.html") + hash;

const PRODUCT_LINKS = [
  { icon: "phone", title: "ตรวจเบอร์โทร", desc: "เทียบกับเบอร์ที่ถูกแจ้งว่าเป็นมิจฉาชีพ ฟรี", href: () => home("#checker") },
  { icon: "message", title: "ตรวจข้อความ SMS / LINE", desc: "AI ชี้จุดที่เข้าข่ายหลอกลวง", href: () => home("#features") },
  { icon: "mic", title: "ตรวจไฟล์เสียง", desc: "จับเสียงสังเคราะห์ / voice clone", href: () => home("#features") },
  { icon: "wave", title: "ตรวจระหว่างสาย", desc: "AI ฟังสดทุก 2 วินาที เตือนทันที", href: () => pageUrl("live.html") },
  { icon: "list", title: "เบอร์อันตราย", desc: "รายชื่อเบอร์ที่ผู้ใช้ช่วยกันแจ้ง", href: () => pageUrl("numbers.html") },
  { icon: "users", title: "แจ้งเตือนครอบครัว", desc: "ส่งต่อคำเตือนให้ลูกหลานเมื่อเสี่ยงสูง", href: () => home("#features") },
];

const HELP_LINKS = [
  { icon: "info", title: "คำถามที่พบบ่อย", desc: "ผลตรวจหมายถึงอะไร เก็บข้อมูลไหม", href: () => home("#faq") },
  { icon: "mail", title: "ติดต่อทีมงาน", desc: "ตอบกลับทางอีเมลภายใน 1-2 วันทำการ", href: () => home("#contact") },
  { icon: "alert", title: "โดนหลอกโอนเงินแล้ว", desc: "โทร 1441 อายัดบัญชีได้ 24 ชั่วโมง", href: () => "tel:1441" },
];

function megaLinks(items) {
  return items.map((l) => `<a href="${l.href()}"><span class="mi">${icon(l.icon)}</span><span><strong>${l.title}</strong><span class="d">${l.desc}</span></span></a>`).join("");
}

function siteHeaderHtml({ authHtml }) {
  return `
    <div class="container">
      <a class="brand" href="${home()}">${brandHtml()}</a>
      <nav class="nav landing-nav" aria-label="เมนูหลัก">
        <div class="nav-item">
          <button type="button" aria-expanded="false">ผลิตภัณฑ์${icon("chev", "icon chev")}</button>
          <div class="mega">
            <div class="mega-links">${megaLinks(PRODUCT_LINKS)}</div>
            <a class="mega-promo" href="${pageUrl("demo.html")}">
              <span class="tag">ใหม่</span>
              ${icon("phone", "icon icon-xl")}
              <h4>เดโมโทรศัพท์: ฟังสายมิจฉาชีพจริง</h4>
              <p>กดรับสาย ฟังเสียงจริง แล้วดู AwayCall ประเมินความเสี่ยงสด ๆ</p>
              <span class="go">ลองเลย ${icon("arrow", "icon arrow")}</span>
            </a>
          </div>
        </div>
        <a href="${home("#features")}">วิธีทำงาน</a>
        <a href="${pageUrl("demo.html")}">เดโม</a>
        <a href="${home("#pricing")}">ราคา</a>
        <div class="nav-item">
          <button type="button" aria-expanded="false">ช่วยเหลือ${icon("chev", "icon chev")}</button>
          <div class="mega narrow"><div class="mega-links">${megaLinks(HELP_LINKS)}</div></div>
        </div>
      </nav>
      <div class="topbar-end">
        ${authHtml}
        <button class="menu-toggle" type="button" aria-label="เปิดเมนู" data-menu-open>${icon("menu", "icon icon-lg")}</button>
      </div>
    </div>`;
}

function mobileMenuHtml(authHtml) {
  const link = (l) => `<a class="mm-link" href="${l.href()}">${icon(l.icon)}<span>${l.title}</span></a>`;
  return `
    <div class="mm-top"><a class="brand" href="${home()}">${brandHtml()}</a>
      <button class="menu-toggle" style="display:grid" type="button" aria-label="ปิดเมนู" data-menu-close>${icon("close", "icon icon-lg")}</button></div>
    <h5>ผลิตภัณฑ์</h5>${PRODUCT_LINKS.map(link).join("")}
    ${link({ icon: "presentation", title: "เดโมโทรศัพท์", href: () => pageUrl("demo.html") })}
    <h5>ช่วยเหลือ</h5>${HELP_LINKS.map(link).join("")}
    ${link({ icon: "sparkle", title: "ราคา", href: () => home("#pricing") })}
    <div class="mm-cta">${authHtml}</div>`;
}

/* แถบเมนูของเว็บ: overlay = ลอยใสบน hero สีเข้ม แล้วเปลี่ยนเป็นสีขาวเมื่อเลื่อนลง */
function mountSiteHeader({ overlay = false, next = "" } = {}) {
  const signedIn = getToken() && getCurrentUser();
  const q = next ? `&next=${encodeURIComponent(next)}` : "";
  const authHtml = signedIn
    ? `<a class="btn btn-primary btn-sm" href="${pageUrl("check.html")}">เข้าใช้งาน</a>`
    : `<a class="btn btn-ghost btn-sm hide-tablet" href="${pageUrl("login.html")}${next ? `?next=${encodeURIComponent(next)}` : ""}">เข้าสู่ระบบ</a>
       <a class="btn btn-primary btn-sm" href="${pageUrl("login.html")}?mode=register${q}">สมัครฟรี</a>`;
  const header = document.getElementById("shell");
  header.className = `topbar${overlay ? " overlay" : ""}`;
  header.innerHTML = siteHeaderHtml({ authHtml });

  const menu = document.createElement("div");
  menu.className = "mobile-menu";
  menu.setAttribute("role", "dialog");
  menu.setAttribute("aria-label", "เมนู");
  menu.innerHTML = mobileMenuHtml(signedIn ? authHtml : authHtml.replace(/ hide-tablet/g, "").replace(/btn-sm/g, "btn-lg btn-block"));
  document.body.appendChild(menu);
  header.querySelector("[data-menu-open]").addEventListener("click", () => { menu.classList.add("open"); document.body.style.overflow = "hidden"; });
  const closeMenu = () => { menu.classList.remove("open"); document.body.style.overflow = ""; };
  menu.querySelector("[data-menu-close]").addEventListener("click", closeMenu);
  menu.querySelectorAll("a").forEach((a) => a.addEventListener("click", closeMenu));

  // mega menu: เปิดเมื่อชี้ (เดสก์ท็อป) หรือคลิก/แตะ, ปิดเมื่อคลิกที่อื่นหรือกด Esc
  const items = [...header.querySelectorAll(".nav-item")];
  const setOpen = (item, open) => {
    item.classList.toggle("open", open);
    item.querySelector("button").setAttribute("aria-expanded", String(open));
  };
  items.forEach((item) => {
    let timer;
    item.addEventListener("mouseenter", () => { clearTimeout(timer); items.forEach((o) => setOpen(o, o === item)); });
    item.addEventListener("mouseleave", () => { timer = setTimeout(() => setOpen(item, false), 160); });
    item.querySelector("button").addEventListener("click", () => setOpen(item, !item.classList.contains("open")));
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".nav-item")) items.forEach((o) => setOpen(o, false)); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { items.forEach((o) => setOpen(o, false)); closeMenu(); } });

  if (overlay) {
    const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }
}

function siteFooterHtml() {
  const col = (title, links) => `<div><h5>${title}</h5><ul>${links.map(([t, h]) => `<li><a href="${h}">${t}</a></li>`).join("")}</ul></div>`;
  return `
    <div class="container">
      <div class="footer-grid">
        <div>
          <a class="brand" href="${home()}">${brandHtml()}</a>
          <p class="footer-blurb">ตรวจเบอร์ ข้อความ และเสียงก่อนเชื่อ ให้ AI ช่วยฟังสายระหว่างคุย แล้วเตือนทันทีเมื่อเข้าข่ายแก๊งคอลเซ็นเตอร์</p>
          <div class="footer-sos">${icon("phone")}<span>โดนหลอกโอนเงิน โทรอายัดบัญชี</span><a href="tel:1441"><b>1441</b></a></div>
        </div>
        ${col("ผลิตภัณฑ์", [["ตรวจเบอร์ / ข้อความ / เสียง", home("#checker")], ["ตรวจระหว่างสาย", pageUrl("live.html")], ["เดโมโทรศัพท์", pageUrl("demo.html")], ["เบอร์อันตราย", pageUrl("numbers.html")], ["ราคา", home("#pricing")]])}
        ${col("ช่วยเหลือ", [["คำถามที่พบบ่อย", home("#faq")], ["ติดต่อเรา", home("#contact")], ["เข้าสู่ระบบ", pageUrl("login.html")], ["สมัครสมาชิก", pageUrl("login.html") + "?mode=register"]])}
        ${col("หน่วยงานที่เกี่ยวข้อง", [["สายด่วน 1441 (AOC)", "tel:1441"], ["แจ้งความออนไลน์", "https://thaipoliceonline.go.th"], ["ตำรวจไซเบอร์ 1441", "tel:1441"]])}
      </div>
      <div class="footer-bottom">
        <span>© 2026 ${APP_NAME} · โครงงานนักศึกษา DetectCallcenter</span>
        <span>ไม่เก็บไฟล์เสียงหรือข้อความของคุณ · ผลตรวจช่วยประกอบการตัดสินใจ ไม่ใช่คำตัดสิน</span>
      </div>
    </div>`;
}

function mountSiteFooter() {
  const footer = document.getElementById("site-footer");
  if (!footer) return;
  footer.className = "footer";
  footer.innerHTML = siteFooterHtml();
}

/* เผยทีละส่วนตอนเลื่อนลง */
function mountReveal() {
  const els = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) { els.forEach((el) => el.classList.add("in")); return; }
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { rootMargin: "0px 0px -8% 0px" });
  els.forEach((el) => io.observe(el));
}

/* ---------------- เมนูของแอป (หลัง login) ---------------- */

const APP_NAV = [
  { href: "check.html", key: "check", label: "ตรวจ", icon: "shield" },
  { href: "live.html", key: "live", label: "ระหว่างสาย", icon: "wave" },
  { href: "demo.html", key: "demo", label: "เดโมสาย", icon: "presentation", desktopOnly: true },
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
      <a class="brand" href="check.html">${brandHtml()}</a>
      <nav class="nav" aria-label="เมนูหลัก">${nav.map(link).join("")}</nav>
      <div class="topbar-end">
        <a class="plan-badge" id="plan-badge" href="account.html"></a>
        <button class="btn btn-ghost btn-sm hide-mobile" data-logout aria-label="ออกจากระบบ" title="ออกจากระบบ">${icon("logout")}</button>
      </div>
    </div>`;
  const tabbar = document.createElement("nav");
  tabbar.className = "tabbar";
  tabbar.setAttribute("aria-label", "เมนูหลัก");
  tabbar.innerHTML = nav.filter((n) => !n.desktopOnly).map(link).join("");
  document.body.appendChild(tabbar);
  document.body.classList.add("has-tabbar", "tint");
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
