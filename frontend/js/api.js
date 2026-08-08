/*
  ตัวช่วยเรียก API กลาง ใช้ร่วมกันทุกหน้า
  ทุกหน้าเรียก endpoint แบบ relative path (/api/...) เพราะ frontend ถูก serve
  จาก FastAPI ตัวเดียวกัน ไม่ต้องกังวลเรื่อง CORS
*/

const API_BASE = "/api";

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

/* แสดง toast แจ้งเตือนเล็กๆ มุมล่างจอ ใช้ร่วมกันทุกหน้า */
function showToast(message, duration = 2600) {
  let toast = document.getElementById("global-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "global-toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => {
    toast.classList.remove("show");
  }, duration);
}

/* อ่าน role ผู้ใช้ที่เก็บไว้ตอน login (mock) เพื่อ personalize หน้า dashboard */
function getCurrentUser() {
  const raw = localStorage.getItem("vg_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

function requireLogin() {
  const user = getCurrentUser();
  if (!user) {
    window.location.href = "login.html";
  }
  return user;
}
