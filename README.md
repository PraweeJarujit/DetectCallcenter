# DetectCallcenter — VoiceGuard AI

ระบบตรวจจับแก๊งคอลเซ็นเตอร์ (FastAPI + PostgreSQL + Nginx) รันทั้งระบบด้วย Docker Compose

<div align="center">

## 📊 Progress ของโปรเจกต์: **90%**

![Progress](https://img.shields.io/badge/Progress-90%25-brightgreen?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-77%20cases-blue?style=for-the-badge)
![Coverage](https://img.shields.io/badge/Coverage-98%25-brightgreen?style=for-the-badge)
![Deploy](https://img.shields.io/badge/Cloud%20Deploy-pending-orange?style=for-the-badge)

```
████████████████████████████████████░░░░  90%
```

</div>

คิดตามน้ำหนักการประเมินของรายวิชา (Week 3-6 = 30%, Week 7-10 = 40%, Week 11-12 = 30%)

| ช่วง | น้ำหนัก | ได้แล้ว | สถานะ | สิ่งที่ยังขาด |
|---|---:|---:|---|---|
| Week 3-6 · Project extension + Database design | 30% | **30%** | ✅ เสร็จ | — |
| Week 7-10 · Full-stack integration + Tests | 40% | **40%** | ✅ เสร็จ | — |
| Week 11-12 · Final project (live + docs) | 30% | **20%** | 🟡 เกือบเสร็จ | ยังไม่ได้ deploy ขึ้น cloud จริง (มี `render.yaml` พร้อมแล้ว) · ยังไม่ได้ทดสอบ `docker compose up --build` บนเครื่องทีม |
| **รวม** | **100%** | **90%** | | |

งานนอก roadmap: ✅ DB Indexing (ทำครบ + วัดผลแล้ว ดู [`db-indexing/`](db-indexing/README.md)) · ⏳ เชื่อมโมเดล AI วิเคราะห์เสียงจริง (`voiceguard-ai`) — ตอนนี้ `/detect/audio` ยังคืนผลจำลอง

### ✅ / ⏳ Checklist ตาม Roadmap

| Week | หัวข้อ | สถานะ |
|---|---|---|
| 3-4 | Pydantic validation · request/response schema · error handling + HTTP status · custom validators/exceptions · logging | ✅ ✅ ✅ ✅ ✅ |
| 5-6 | FK + 1-N / N-N · SQLAlchemy relationships · แก้ N+1 · indexing · normalization (≥ 2-3 ตาราง → มี 8 ตาราง) | ✅ ✅ ✅ ✅ ✅ |
| 7-8 | Fetch + async/await · GET/POST/PUT/DELETE · จัดการ error ฝั่งหน้าเว็บ · state · dashboard/admin | ✅ ✅ ✅ ✅ ✅ |
| 9-10 | pytest · API tests · DevTools/Network (`X-Request-ID`) · logging/debug · integration tests · coverage ≥ 70% (ได้ 98%) | ✅ ✅ ✅ ✅ ✅ ✅ |
| 11-12 | CORS/CSRF/XSS · JWT best practice · env/secrets · Dockerize FastAPI + PostgreSQL · **deploy ขึ้น cloud** | ✅ ✅ ✅ ✅ ⏳ |

> ⏳ = ยังไม่เสร็จ · Docker ยังไม่ได้ build จริงบนเครื่องทีม (โค้ดและ config ผ่านการตรวจ + ทดสอบขั้นตอน start ของ container แล้ว)

## สิ่งที่ทำตาม Web-Dev-Roadmap (Week 3-12)

| สัปดาห์ | หัวข้อ | สิ่งที่มีในโปรเจกต์ |
|---|---|---|
| 3-4 | API Validation & Error Handling | Pydantic schema + custom validators (`core/validators.py`: normalize เบอร์ไทย, รหัสผ่านต้องมีตัวอักษร+ตัวเลข, ห้ามสมัครเป็น admin) · custom exceptions + global handler ให้ error รูปแบบเดียว `{success, error:{code,message,details}, request_id}` (`core/exceptions.py`) · logging พร้อม request id + เวลาตอบสนอง (`core/logging.py`) |
| 5-6 | Database Relations & Query Optimization | 8 ตาราง: One-to-Many (users→reports/call_logs/emergency_contacts, blacklist_numbers→reports) + Many-to-Many (reports↔scam_categories) · SQLAlchemy `relationship` + eager loading แก้ N+1 · normalization (reports อ้าง FK แทนเก็บเบอร์ซ้ำ) · **Indexing → ดู [`db-indexing/`](db-indexing/README.md)** · Alembic migration |
| 7-8 | Frontend Integration | `js/api.js` (Fetch + async/await, JWT, timeout, จัดการ error) · Login/Register จริง · Dashboard ดึงข้อมูลจริง + keyset "โหลดเพิ่ม" · Settings = CRUD ผู้ติดต่อฉุกเฉินครบ GET/POST/PUT/DELETE · หน้า **Blacklist (admin interface)** ค้นหา/กรอง/แบ่งหน้า/เพิ่ม/แก้/ลบ |
| 9-10 | Testing & Debugging | pytest 77 tests (unit + API + integration) **coverage 98%** (เกณฑ์ ≥ 70%) รันได้ทั้ง SQLite และ PostgreSQL · test ยืนยันว่าไม่มี N+1 · `X-Request-ID` ใช้ไล่ log คู่กับ DevTools > Network |
| 11-12 | Security & Deployment | CORS จำกัด origin · security headers + CSP · escape HTML กัน XSS ทุกจุด · rate limit login · JWT revoke ตอน logout · secret ผ่าน env (production ไม่ยอมสตาร์ทถ้าใช้ secret ตัวอย่าง) · Docker รันด้วย non-root · `render.yaml` deploy ขึ้น Render |

## โครงสร้าง

```
docker-compose.yml            db + backend + frontend(nginx)
render.yaml                   Blueprint สำหรับ deploy ขึ้น Render
backend/
  Dockerfile, docker-entrypoint.sh   (alembic upgrade -> seed -> uvicorn)
  requirements.txt, requirements-dev.txt
  .env.example                <- คัดลอกเป็น .env ก่อนรัน
  alembic/versions/
    0001_initial_schema.py         ตาราง + PK/UNIQUE/FK + หมวดการหลอกลวงตั้งต้น
    0002_performance_indexes.py    index เพื่อ performance (IDX-2..9)
  app/
    main.py                   รวม router + middleware + exception handler
    seed.py                   ข้อมูลตั้งต้น/ผู้ใช้ทดลอง (python -m app.seed)
    core/                     config, security(JWT/bcrypt), exceptions, logging, validators, rate_limit
    models/                   User, BlacklistNumber, Report, ScamCategory(+report_categories), CallLog, EmergencyContact, TokenBlacklist
    schemas/                  Pydantic request/response
    routers/                  auth, users, detect, calls, contacts
  tests/                      pytest (conftest + 7 ไฟล์)
frontend/
  nginx.conf                  เสิร์ฟหน้าเว็บ + proxy /api -> backend + security headers
  js/api.js                   Fetch helper กลาง
  pages/                      login, dashboard, blacklist, settings, report-summary, call-demo
db-indexing/                  lab index บน schema จริง + benchmark + ผลวัด
indexing-lab/                 lab ต้นฉบับจากรายวิชา
```

## 1. ติดตั้งและตั้งค่า

```bash
cp backend/.env.example backend/.env
```

เปิด `backend/.env` แล้วแก้:
- `POSTGRES_PASSWORD` และรหัสผ่านใน `DATABASE_URL` ให้ตรงกัน
- `JWT_SECRET_KEY` — สร้างด้วย `openssl rand -hex 32` (**ห้ามใช้ค่าตัวอย่าง**)

## 2. รันด้วย Docker Compose

```bash
docker compose up -d --build
docker compose ps              # db / backend / frontend ต้องเป็น healthy
docker compose logs -f backend
```

ตอน backend สตาร์ทจะ (1) `alembic upgrade head` สร้าง/อัปเดตตารางและ index (2) seed ข้อมูลตั้งต้น
(3) เปิด API — ถ้าเคยรันเวอร์ชันเก่าที่ใช้ `create_all` มาก่อน ให้ `docker compose down -v` หนึ่งครั้งเพื่อเริ่มฐานข้อมูลใหม่

| | URL |
|---|---|
| หน้าเว็บ | http://localhost:3000 |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL (DBeaver) | localhost:5434 (user/pass ตาม `.env`) |

บัญชีทดลอง (สร้างเมื่อ `SEED_DEMO_DATA=true`): `officer.demo` / `demo1234`, `bank.demo` / `demo1234`, admin: `admin` / `Admin1234`

## 3. วิธีรันทดสอบ (Testing)

> ต้องใช้ **Python 3.12** (ตรงกับ Docker image) — Python 3.13 ติดตั้งแพ็กเกจบางตัวในเวอร์ชันที่ล็อกไว้ไม่ได้

### 3.1 Unit / API tests ด้วย pytest (ไม่ต้องมี Docker และไม่ต้องมี PostgreSQL)

ค่าเริ่มต้น test ใช้ SQLite ชั่วคราว สร้าง/ลบเองอัตโนมัติ — ไม่แตะฐานข้อมูลจริง

**Windows (PowerShell)**

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # ถ้าโดนบล็อก: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements-dev.txt
pytest
```

**macOS / Linux**

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

ผลที่ควรได้: `77 passed` และบรรทัด `Required test coverage of 70% reached. Total coverage: 9x%`
(ถ้า coverage ต่ำกว่า 70% pytest จะ fail ทันที — ตั้งไว้ใน `pytest.ini`)

คำสั่งที่ใช้บ่อย:

```bash
pytest tests/test_auth.py              # รันทีละไฟล์
pytest -k "blacklist"                  # รันเฉพาะ test ที่ชื่อมีคำว่า blacklist
pytest -x -vv                          # หยุดที่ test แรกที่พัง + แสดงรายละเอียด
pytest --cov-report=html               # สร้างรายงาน coverage เป็นหน้าเว็บที่ htmlcov/index.html
```

| ไฟล์ test | ทดสอบอะไร |
|---|---|
| `test_unit_validators.py` | validator เบอร์โทร/รหัสผ่าน, JWT, bcrypt, rate limiter, config production |
| `test_auth.py` | สมัคร, login, rate limit, logout แล้ว token ใช้ไม่ได้, เปลี่ยนรหัสผ่าน |
| `test_users.py` | สิทธิ์ user / admin, แก้ไข, ลบ |
| `test_detect.py` | ตรวจเบอร์, report + หมวด (N-N), blacklist CRUD, ลบแล้ว cascade, ไฟล์เสียง |
| `test_calls.py` | dashboard: สถิติวันนี้, แนวโน้ม 7 วัน, keyset pagination |
| `test_contacts.py` | CRUD ผู้ติดต่อฉุกเฉิน + กันแก้ของคนอื่น (IDOR) |
| `test_integration.py` | flow ผู้ใช้ตั้งแต่สมัครถึง logout, รูปแบบ error, security headers, CORS, **ไม่มี N+1**, seed |

### 3.2 รัน test บน PostgreSQL จริง (แนะนำก่อนส่งงาน)

เปิดระบบด้วย Docker ก่อน (หัวข้อ 2) แล้วสร้างฐานข้อมูลแยกสำหรับ test — **อย่าชี้ไปที่ฐานข้อมูลหลัก เพราะ test จะล้างข้อมูลทุกตาราง**

```bash
docker compose exec db psql -U dcc_user -d detectcallcenter -c "CREATE DATABASE dcc_test"
cd backend
# PowerShell: $env:TEST_DATABASE_URL="postgresql://dcc_user:<รหัสใน .env>@localhost:5434/dcc_test"
export TEST_DATABASE_URL="postgresql://dcc_user:<รหัสใน .env>@localhost:5434/dcc_test"
pytest
```

### 3.3 ทดสอบผ่านหน้าเว็บ (manual test)

หลัง `docker compose up -d --build` เปิด http://localhost:3000 แล้วไล่ตามนี้:

| # | ขั้นตอน | ผลที่ควรเห็น |
|---|---|---|
| 1 | เปิด `dashboard.html` โดยยังไม่ login | ถูกพาไปหน้า login |
| 2 | login `officer.demo` แต่ใส่รหัสผิด | ข้อความ "Username หรือ password ไม่ถูกต้อง" |
| 3 | login `officer.demo` / `demo1234` | Dashboard มีตัวเลข, กราฟ 7 วัน, Call Logs + ปุ่ม "โหลดเพิ่ม" |
| 4 | Settings → เพิ่ม / ✎ แก้ / ✕ ลบ ผู้ติดต่อ, ลองใส่เบอร์ `12` | CRUD ทำงาน, เบอร์ผิดขึ้น toast สีแดง |
| 5 | Call Demo → รับสาย → วางสายทันที → เลือกหมวด → แจ้งเบาะแส | "ส่งรายงานเบอร์ ... สำเร็จ" |
| 6 | Blacklist → ค้น `0641234521` → ดู | เห็น report ที่เพิ่งแจ้ง |
| 7 | logout แล้ว login `admin` / `Admin1234` → Blacklist | มีปุ่ม + เพิ่มเบอร์ / แก้ไข / ลบ |
| 8 | เปิด DevTools (F12) → Network → คลิก request `/api/...` | Response header มี `X-Request-ID` ใช้ค้นใน `docker compose logs backend` |

### 3.4 ทดสอบ API ด้วย Swagger

เปิด http://localhost:8000/docs → `POST /api/login` → copy `access_token` → กดปุ่ม **Authorize** มุมขวาบน ใส่ token → ลองเรียก endpoint อื่นได้เลย

### 3.5 ทดสอบ performance ของ index

ดูขั้นตอนใน [`db-indexing/README.md`](db-indexing/README.md) (เปิด PostgreSQL 2 ตัว มี/ไม่มี index แล้วรัน `scripts/benchmark.py`)

## 4. API หลัก

| Method | Path | สิทธิ์ | หมายเหตุ |
|---|---|---|---|
| POST | `/api/register`, `/api/login`, `/api/logout`, `/api/change-password` | - / - / login / login | login ผิดเกิน 5 ครั้ง/นาที → 429 |
| GET | `/api/me`, `/api/users/{id}` · PUT `/api/users/{id}` | login | แก้ได้เฉพาะตัวเอง (admin แก้ได้ทุกคน) |
| GET/DELETE | `/api/users`, `/api/users/{id}` | admin | |
| POST | `/api/detect/number` | - | บันทึก call log ทุกครั้ง |
| POST | `/api/detect/audio` | login | ส่งต่อ voiceguard-ai หรือ fallback mock (`is_mock: true`) |
| POST | `/api/report` · GET `/api/reports/me` · GET `/api/categories` | login / login / - | report เลือกหมวดได้หลายหมวด |
| GET | `/api/blacklist?q=&status=&page=` | - | `q` = เบอร์ที่ขึ้นต้นด้วย |
| GET | `/api/blacklist/{phone}` | login | พร้อม report ล่าสุด 50 รายการ |
| POST/PUT/DELETE | `/api/blacklist`, `/api/blacklist/{phone}` | admin | |
| GET | `/api/calls/stats`, `/api/calls/trend`, `/api/calls/logs?before_id=&mine=` | login | dashboard |
| POST | `/api/calls` · GET `/api/calls/demo-analysis` | - | หน้า Call Demo |
| GET/POST/PUT/DELETE | `/api/contacts`, `/api/contacts/{id}` | login | ผู้ติดต่อฉุกเฉินของตัวเอง |

ตัวอย่าง:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/login -H "Content-Type: application/json" \
  -d '{"username":"officer.demo","password":"demo1234"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/detect/number -H "Content-Type: application/json" \
  -d '{"phone_number":"081-234-5678"}'

curl -X POST http://localhost:8000/api/report -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"phone_number":"0812345678","risk_score":90,"note":"หลอกให้โอนเงิน","category_codes":["impersonate_police"]}'

curl "http://localhost:8000/api/blacklist?q=0812&status=high_risk&page=1&page_size=20"
```

ทุก error ตอบรูปแบบเดียวกัน เช่น 422:

```json
{"success": false,
 "error": {"code": "VALIDATION_ERROR", "message": "ข้อมูลที่ส่งมาไม่ถูกต้อง: เบอร์โทรต้องเป็นเบอร์ไทย 9-10 หลัก ...",
           "details": [{"field": "phone_number", "message": "...", "type": "value_error"}]},
 "request_id": "3f2a9c1d0b7e4a51"}
```

## 5. Security (Week 11-12)

- **XSS**: frontend escape ทุกค่าก่อนใส่ `innerHTML` (`escapeHtml`) + CSP จาก Nginx · API ตอบ JSON พร้อม `Content-Security-Policy: default-src 'none'`
- **CSRF**: ใช้ JWT ใน header `Authorization` (ไม่ใช้ cookie) browser จึงไม่แนบ token ให้เองเวลาโดนหลอกให้ส่ง request ข้ามเว็บ — และ CORS ปิด `allow_credentials`
- **CORS**: อนุญาตเฉพาะ origin ใน `CORS_ORIGINS` (production ห้าม `*`)
- **Auth**: bcrypt · JWT มี `jti` + revoke ตอน logout · rate limit login · ข้อความ error เดียวกันทั้ง "ไม่มี user" และ "รหัสผิด" · สมัครเป็น admin เองไม่ได้ · ดู/แก้ข้อมูลคนอื่นได้เฉพาะ admin · ผู้ติดต่อของคนอื่นตอบ 404 (กัน IDOR)
- **Secrets**: อยู่ใน `.env` (ถูก gitignore) · `ENVIRONMENT=production` จะไม่ยอมสตาร์ทถ้า `JWT_SECRET_KEY` เป็นค่าตัวอย่าง/สั้นกว่า 32 ตัว
- **Container**: backend รันด้วย user ที่ไม่ใช่ root · DB port bind เฉพาะ `127.0.0.1`
- error 500 ไม่ส่ง stack trace กลับให้ client (log ฝั่ง server พร้อม request id)

## 6. Deploy ขึ้น Cloud (Render)

1. push repo ขึ้น GitHub
2. Render Dashboard → **New → Blueprint** → เลือก repo → Render อ่าน `render.yaml` แล้วสร้าง PostgreSQL + API (Docker) + หน้าเว็บ (static) ให้
3. แก้ `CORS_ORIGINS` และปลายทาง rewrite `/api/*` ใน `render.yaml` ให้ตรงกับ URL จริงที่ Render ให้มา
4. ระบบจริงตั้ง `SEED_DEMO_DATA=false` แล้วสร้าง admin เอง

(Railway/Heroku ใช้ Dockerfile เดียวกันได้ — `DATABASE_URL` แบบ `postgres://` ถูกแปลงให้อัตโนมัติ, พอร์ตอ่านจาก `$PORT`)

## 7. หมายเหตุ

- **`/detect/audio`** เป็นจุดเชื่อมต่อไปยังโมเดล AI จริงผ่าน `VOICEGUARD_AI_URL` — ถ้ายังไม่มีบริการ AI จะคืนผลจำลอง (`is_mock: true`) เมื่อทีม AI พร้อม (รับไฟล์ที่ `/analyze` คืน `{risk_score, is_synthetic_voice, detail}`) ก็เพิ่ม service เข้า `docker-compose.yml` ได้เลย
- เปลี่ยน schema: แก้ model แล้ว `alembic revision --autogenerate -m "..."` → ตรวจไฟล์ที่ได้ → `alembic upgrade head` (`alembic check` ใช้ยืนยันว่า model กับ migration ตรงกัน)
