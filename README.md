# DetectCallcenter API

Backend REST API (FastAPI + PostgreSQL) สำหรับระบบ DetectCallcenter รันด้วย Docker Compose

## โครงสร้างที่เพิ่มเข้ามา

```
docker-compose.yml
backend/
  Dockerfile
  requirements.txt
  .env.example          <- คัดลอกเป็น .env ก่อนรัน
  app/
    main.py             <- entrypoint, รวม router + CORS + auto-create tables
    database.py          <- SQLAlchemy engine/session
    dependencies.py      <- get_current_user / require_admin (JWT guard)
    core/
      config.py           <- อ่านค่า settings จาก .env
      security.py          <- hash password, สร้าง/ตรวจ JWT
    models/                <- SQLAlchemy models (User, TokenBlacklist, BlacklistNumber, Report)
    schemas/                <- Pydantic request/response schemas
    routers/
      auth.py                <- /register /login /logout /change-password
      users.py                 <- /me /users /users/{id} /check-username/{name}
      detect.py                 <- /detect/number /detect/audio /report /blacklist
```

## 1. ติดตั้งและตั้งค่า

```bash
cp backend/.env.example backend/.env
```

เปิด `backend/.env` แล้วแก้:
- `POSTGRES_PASSWORD` — ตั้งรหัสผ่านให้แข็งแรง
- `JWT_SECRET_KEY` — สร้างด้วย `openssl rand -hex 32` แล้วนำมาใส่ **ห้ามใช้ค่าตัวอย่างใน production**
- `DATABASE_URL` — ต้องตรงกับ user/password/db ที่ตั้งไว้ (ค่า default ใช้ชื่อ service `db` ตาม docker-compose)

## 2. รันด้วย Docker Compose

```bash
docker-compose up -d --build
```

คำสั่งนี้จะ:
1. ดึง/สร้าง image ของ Postgres, backend (FastAPI) และ Nginx (เสิร์ฟ frontend static)
2. รอจน Postgres พร้อม (`healthcheck`) แล้วค่อยสตาร์ท backend
3. ตอน backend สตาร์ทครั้งแรกจะสร้างตาราง (users, reports, blacklist_numbers, token_blacklist) ให้อัตโนมัติ

ตรวจสอบว่า container รันอยู่:
```bash
docker-compose ps
```

ดู log ของ backend:
```bash
docker-compose logs -f backend
```

หยุดการทำงาน:
```bash
docker-compose down          # หยุด + ลบ container (ข้อมูลใน volume ยังอยู่)
docker-compose down -v       # หยุด + ลบ container + ลบข้อมูลฐานข้อมูลทั้งหมด
```

## 3. เข้าถึง API

- Backend API: http://localhost:8000/api
- Swagger UI (ทดสอบ API แบบ interactive): **http://localhost:8000/docs**
- Frontend (ถ้าใช้ service nginx ที่เพิ่มให้): http://localhost:8080

## 4. ตัวอย่างการเรียกใช้งาน (curl)

สมัครสมาชิก:
```bash
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username":"officer.somchai","email":"somchai@example.gov.th","password":"StrongPass123","role":"gov"}'
```

เข้าสู่ระบบ (ได้ JWT กลับมา):
```bash
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"officer.somchai","password":"StrongPass123"}'
```

เรียก endpoint ที่ต้อง login (ใส่ token ที่ได้จากขั้นตอนก่อนหน้า):
```bash
curl http://localhost:8000/api/me \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

ตรวจสอบเบอร์โทร (ไม่ต้อง login):
```bash
curl -X POST http://localhost:8000/api/detect/number \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0812345678"}'
```

แจ้งรีพอร์ตเบอร์มิจฉาชีพ (ต้อง login):
```bash
curl -X POST http://localhost:8000/api/report \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"0812345678","risk_score":90,"note":"หลอกให้โอนเงิน"}'
```

ดูแบล็คลิสต์ (pagination):
```bash
curl "http://localhost:8000/api/blacklist?page=1&page_size=20"
```

## 5. หมายเหตุสำคัญ

- **`/detect/audio`** เป็นจุดเชื่อมต่อไปยังโมเดล AI จริงในโฟลเดอร์ `voiceguard-ai/` ผ่านตัวแปร
  `VOICEGUARD_AI_URL` ใน `.env` — ถ้ายังไม่มีบริการ AI จริง endpoint จะ fallback เป็นผลจำลอง
  (mock) โดยอัตโนมัติ เพื่อไม่ให้ frontend พังระหว่างพัฒนา เมื่อทีม AI พร้อม service จริง (เช่น
  รับไฟล์เสียงที่ path `/analyze` แล้วคืน JSON `{risk_score, is_synthetic_voice, detail}`)
  ก็เพิ่ม service นั้นเข้า `docker-compose.yml` แล้วชี้ `VOICEGUARD_AI_URL` ไปหาได้เลย
- **Logout** ใช้วิธีเก็บ `jti` (JWT ID) ของ token ที่ logout แล้วลงตาราง `token_blacklist` เพราะ
  JWT เป็น stateless โดยธรรมชาติ — ทุก request ที่ต้อง login จะเช็คตารางนี้ก่อนเชื่อถือ token
- โค้ดใช้ `Base.metadata.create_all()` สร้างตารางอัตโนมัติตอน startup เพื่อความสะดวกช่วง demo/dev
  เมื่อจะขึ้น production จริงแนะนำเปลี่ยนไปใช้ **Alembic migration** แทน (มี `alembic` อยู่ใน
  `requirements.txt` แล้ว รันคำสั่ง `alembic init alembic` ในโฟลเดอร์ `backend/` เพื่อเริ่มตั้งค่า)
- endpoint ที่แก้ไข/ลบ user คนอื่น หรือลบ user ได้ ถูกจำกัดสิทธิ์ไว้แล้ว (เจ้าของบัญชี หรือ
  role `admin` เท่านั้น) — สร้าง user แรกให้เป็น admin ได้โดย register ปกติแล้วไป update
  `role` ในฐานข้อมูลตรง ๆ ครั้งเดียว หรือเพิ่ม seed script ภายหลัง
- `docker-compose.yml` เปิด `CORSMiddleware` แบบ `allow_origins=["*"]` ไว้เพื่อความสะดวกตอน
  demo เท่านั้น ก่อนขึ้น production ให้จำกัดเป็นโดเมนจริงของ frontend ใน `backend/app/main.py`
