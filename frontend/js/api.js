/*
  ตัวช่วยเรียก API กลาง ใช้ร่วมกันทุกหน้า (Week 7-8: Fetch API + async/await)

  - เรียก endpoint แบบ relative path (/api/...) เพราะ Nginx (frontend) proxy /api ไปหา backend
    ให้อยู่ origin เดียวกัน -> ไม่ติด CORS และไม่ต้องรู้ URL ของ backend
    (ถ้าเปิดหน้าเว็บจากที่อื่น ตั้ง window.VG_API_BASE = "http://localhost:8000/api" ก่อนโหลดไฟล์นี้ได้)
  - แนบ JWT (Authorization: Bearer) ให้อัตโนมัติ
  - แปลง error รูปแบบกลางของ backend {success:false, error:{code,message,details}} เป็น ApiError
  - 401 -> ล้าง session แล้วพาไปหน้า login (ยกเว้นเรียกแบบ {auth:false})
*/

const API_BASE = window.VG_API_BASE || "/api";
const TOKEN_KEY = "vg_token";
const USER_KEY = "vg_user";
const REQUEST_TIMEOUT_MS = 15000;

class ApiError extends Error {
  constructor(status, code, message, details, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;       // HTTP status (0 = ต่อ server ไม่ได้)
    this.code = code;           // เช่น VALIDATION_ERROR, NOT_FOUND
    this.details = details;
    this.requestId = requestId; // ใช้ค้น log ฝั่ง backend
  }
}

/* ---------------- session ---------------- */

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getCurrentUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function updateStoredUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function isAdmin() {
  const u = getCurrentUser();
  return !!u && u.role === "admin";
}

/* หน้าไหนต้อง login ให้เรียกตัวนี้บนสุด -> ไม่มี token ก็เด้งไปหน้า login พร้อมจำหน้าเดิม */
function requireLogin() {
  const user = getCurrentUser();
  if (!user || !getToken()) {
    const next = encodeURIComponent(location.pathname.split("/").pop() + location.search);
    window.location.href = `login.html?next=${next}`;
    return null;
  }
  return user;
}

async function logout() {
  try {
    if (getToken()) await apiPost("/logout", {}, { auth: true, redirectOn401: false });
  } catch (e) {
    /* token หมดอายุแล้วก็ไม่เป็นไร */
  }
  clearSession();
  window.location.href = "login.html";
}

/* ---------------- core request ---------------- */

async function apiRequest(method, path, body, options = {}) {
  const { auth = true, redirectOn401 = true, isForm = false } = options;
  const headers = {};
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers["Authorization"] = `Bearer ${token}`;

  // ยกเลิก request ที่ค้างนานเกินไป (เช่น server ล่ม) แทนที่จะรอไม่สิ้นสุด
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    const msg = err.name === "AbortError"
      ? "เซิร์ฟเวอร์ตอบช้าเกินไป กรุณาลองใหม่"
      : "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตหรือรอสักครู่";
    throw new ApiError(0, "NETWORK_ERROR", msg);
  } finally {
    clearTimeout(timer);
  }

  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    const err = (data && data.error) || {};
    const apiErr = new ApiError(
      res.status,
      err.code || `HTTP_${res.status}`,
      err.message || `เกิดข้อผิดพลาด (${res.status})`,
      err.details,
      (data && data.request_id) || res.headers.get("X-Request-ID"),
    );
    if (res.status === 401 && auth && token && redirectOn401) {
      clearSession();
      showToast("เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่");
      setTimeout(() => (window.location.href = "login.html"), 900);
    }
    throw apiErr;
  }
  return data;
}

const apiGet = (path, options) => apiRequest("GET", path, undefined, options);
const apiPost = (path, body, options) => apiRequest("POST", path, body ?? {}, options);
const apiPut = (path, body, options) => apiRequest("PUT", path, body ?? {}, options);
const apiDelete = (path, options) => apiRequest("DELETE", path, undefined, options);

/* ---------------- UI helpers ---------------- */

/* กัน XSS: ทุกค่าที่มาจาก API/ผู้ใช้ ต้อง escape ก่อนใส่ลง innerHTML (Week 11-12) */
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* แปลง error เป็นข้อความที่อ่านง่ายสำหรับผู้ใช้ */
function errorMessage(err) {
  if (err instanceof ApiError) return err.message;
  return "เกิดข้อผิดพลาดที่ไม่คาดคิด";
}

/* แสดง toast แจ้งเตือนเล็กๆ มุมล่างจอ ใช้ร่วมกันทุกหน้า (type: info | success | error) */
function showToast(message, duration = 2600, type = "info") {
  let toast = document.getElementById("global-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "global-toast";
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.dataset.type = type;
  toast.classList.add("show");
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, duration);
}

function showError(err) {
  showToast("⚠️ " + errorMessage(err), 3600, "error");
}

/* ปุ่มที่กำลังรอ API: disable + เปลี่ยนข้อความ กันกดซ้ำ */
async function withLoading(button, task, loadingText = "กำลังดำเนินการ...") {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = loadingText;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function formatPhone(phone) {
  const p = String(phone || "");
  if (/^0\d{9}$/.test(p)) return `${p.slice(0, 3)}-${p.slice(3, 6)}-${p.slice(6)}`;
  if (/^0\d{8}$/.test(p)) return `${p.slice(0, 2)}-${p.slice(2, 5)}-${p.slice(5)}`;
  return p;
}

function formatDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

/* แสดงชื่อผู้ใช้ + role ใน sidebar และผูกปุ่ม logout (ใช้ร่วมทุกหน้าที่มี sidebar) */
function renderUserChip() {
  const chip = document.getElementById("role-chip");
  const user = getCurrentUser();
  if (chip) {
    chip.textContent = user
      ? `👤 ${user.username} · ${user.role_label || user.role}`
      : "👤 โหมดผู้เยี่ยมชม (Guest)";
  }
  document.querySelectorAll("[data-logout]").forEach((el) =>
    el.addEventListener("click", (e) => {
      e.preventDefault();
      logout();
    }),
  );
}
