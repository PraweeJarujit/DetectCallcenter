# DB Indexing — นำ Indexing Lab มาใช้กับ DetectCallcenter (AwayCall)

ต่อยอดจาก `indexing-lab/` (ตาราง `transactions` ตัวอย่าง) มาใช้กับ **schema จริงของโปรเจกต์**:
ออกแบบ index จาก query ที่ API ใช้จริง → ใส่ใน SQLAlchemy model + Alembic migration → พิสูจน์ด้วย `EXPLAIN ANALYZE` บนข้อมูลขนาด production

| Service | Port | หมายเหตุ |
|---|---|---|
| pg_app_with_index | 5442 | schema จริง + index IDX-2 ถึง IDX-9 (migration `0002`) |
| pg_app_no_index | 5443 | schema จริง มีแค่ PK / UNIQUE / FK (migration `0001`) |
| adminer | http://localhost:8082 | GUI (System: PostgreSQL, Server: `pg_app_with_index` หรือ `pg_app_no_index`) |

User / Password / DB: `student` / `student` / `appdb` — พอร์ตไม่ชนกับ `indexing-lab` และระบบหลัก รันพร้อมกันได้

ข้อมูลจำลอง (เหมือนกันทั้ง 2 DB ด้วย `setseed`): `call_logs` 2,000,000 · `reports` 600,000 · `report_categories` ~860,000 · `blacklist_numbers` 200,000 · `users` 1,000 — "วันนี้" ของ lab คือ **2026-10-02 (เวลาไทย)**

## เริ่มต้น

```bash
cd db-indexing
docker compose up -d
docker compose logs -f pg_app_no_index     # รอจนเห็น ">>> Seed done" (ประมาณ 1-3 นาที) แล้ว Ctrl+C
docker compose ps                          # ทั้ง 2 ตัวต้องเป็น (healthy)
```

## รัน lab

```bash
docker exec -it pg_app_with_index psql -U student -d appdb -f /labs/01-explain-api.sql
docker exec -it pg_app_no_index   psql -U student -d appdb -f /labs/01-explain-api.sql
```

| ไฟล์ | รันบน | เนื้อหา | เทียบกับ indexing-lab |
|---|---|---|---|
| 01-explain-api.sql | ทั้ง 2 ตัว | EXPLAIN ANALYZE query จริงของ dashboard / blacklist / reports | lab 01 |
| 02-size.sql | ทั้ง 2 ตัว | ขนาด table vs index, partial index เล็กกว่าเท่าไร | lab 02 |
| 03-insert-cost.sql | ทั้ง 2 ตัว | INSERT call_logs 200,000 แถวแล้ว ROLLBACK | lab 03 |
| 04-pitfalls.sql | with_index | function บน column, partial predicate, LIKE, low cardinality, OFFSET vs keyset | lab 04 |
| 05-composite-leftmost.sql | with_index | composite (status, risk_score DESC, id) + leftmost rule + ทิศทาง ORDER BY | lab 05 |
| 06-fk-cascade.sql | with_index | FK ไม่มี index อัตโนมัติ → ลบแถวแม่ช้า (ON DELETE CASCADE / SET NULL) | ใหม่ |
| 07-unused-indexes.sql | with_index | index ไหนไม่ถูกใช้ / ทำไมไม่ทำทุก column | lab 07 |

Benchmark อัตโนมัติ (ได้ตารางผลลัพธ์เป็น Markdown):

```bash
pip install psycopg2-binary
python scripts/benchmark.py --runs 7 --out results/benchmark.md
```

ไฟล์ 01, 02, 03, 05, 07 รันใน DBeaver ได้ (ลบบรรทัด `\timing` / `\echo` ก่อน) ส่วน 04 และ 06 ใช้ตัวแปร psql (`\gset`) ให้รันผ่าน `psql`

---

## 1. ออกแบบ index จาก query จริงของ API

หลักที่ใช้ (จาก indexing-lab): ทำ index เฉพาะ column ที่ **อยู่ใน WHERE / ORDER BY ของ query ที่ถูกเรียกบ่อย** และมี **cardinality สูงพอ** ไม่ทำทุก column เพราะทุก index ทำให้ INSERT/UPDATE ช้าลงและกินพื้นที่

| ID | ตาราง / Index | Query ที่ใช้ (endpoint) | ทำไมออกแบบแบบนี้ |
|---|---|---|---|
| IDX-1 | `blacklist_numbers (phone_number varchar_pattern_ops)` **UNIQUE** | `POST /detect/number`, `POST /report` (`= เบอร์`), `GET /blacklist?q=0812` (`LIKE '0812%'`) | index เดียวทำได้ 2 งาน: btree ปกติบน collation `en_US` ใช้กับ `LIKE 'prefix%'` ไม่ได้ (lab 04 ข้อ 4.3) แต่ `varchar_pattern_ops` รองรับทั้ง `=` และ prefix |
| IDX-2 | `blacklist_numbers (status, risk_score DESC, id)` | `GET /blacklist?status=high_risk` เรียง risk มาก→น้อย หน้าละ 20 | `status` มีแค่ 3 ค่า (index เดี่ยวไม่ช่วย, lab 04 ข้อ 4.4) → ทำ composite ให้ ORDER BY ตรงลำดับ index: อ่าน 20 entry แล้วหยุด ไม่ต้อง Sort |
| IDX-3 | `blacklist_numbers (risk_score DESC, id)` | `GET /blacklist` แบบไม่กรอง | ไม่มี `status` ใน WHERE = ข้าม column ซ้ายสุดของ IDX-2 → ใช้ไม่ได้ (leftmost rule, lab 05) |
| IDX-4 | `reports (blacklist_number_id, created_at DESC)` | `GET /blacklist/{phone}` (report ล่าสุดของเบอร์), `DELETE /blacklist/{phone}` (CASCADE) | **Postgres ไม่สร้าง index ให้ FK อัตโนมัติ** — ไม่มีตัวนี้ ลบเบอร์ 1 เบอร์ = Seq Scan reports 6 แสนแถว (lab 06) |
| IDX-5 | `reports (reported_by, created_at DESC)` | `GET /reports/me` + นับ total, ลบ user (SET NULL) | เรียงใหม่สุดก่อนตรงกับ index, COUNT ได้แบบ Index Only Scan |
| IDX-6 | `call_logs (created_at DESC, id DESC)` | `GET /calls/stats` (วันนี้), `GET /calls/logs` (ล่าสุด + keyset `before_id`) | ทุก query ของ dashboard กรอง/เรียงตามเวลา; ต่อท้าย `id` ให้ลำดับไม่กำกวมและใช้ทำ keyset pagination ได้ |
| IDX-7 | `call_logs (created_at) WHERE risk_score >= 80` **PARTIAL** | `GET /calls/stats` (เสี่ยงสูงวันนี้), `GET /calls/trend` (7 วัน) | เก็บเฉพาะ ~20% ของแถว → **เล็กกว่า IDX-6 ประมาณ 7 เท่า** (8.8 MB vs 60 MB) และทำ Index Only Scan ได้ |
| IDX-8 | `call_logs (user_id, created_at DESC, id DESC) WHERE user_id IS NOT NULL` **PARTIAL** | `GET /calls/logs?mine=true`, ลบ user (SET NULL) | ครึ่งหนึ่งของ call_logs มาจากผู้ไม่ login (`user_id` NULL) และไม่มี query ไหนค้น NULL → ตัดทิ้ง ขนาดลดจาก **86 MB → 47 MB** และ INSERT เร็วขึ้น |
| IDX-9 | `emergency_contacts (user_id)` | `GET /contacts`, ลบ user (CASCADE) | FK index |
| (M-N) | `report_categories (category_id)` | สถิติตามหมวดการหลอกลวง | PK `(report_id, category_id)` ใช้ค้นจากฝั่ง report ได้ แต่ค้นกลับจากหมวดต้องมี index ขึ้นต้นด้วย `category_id` |

Index ที่มีอยู่แล้วจาก UNIQUE (ไม่ต้องสร้างเพิ่ม): `users.username`, `users.email` (login / register), `token_blacklist.jti` (ถูกค้น **ทุก request** ที่ login แล้ว)

### Index ที่ "ตั้งใจไม่ทำ"

| Column | เหตุผล (เทียบกับ lab 07) |
|---|---|
| `call_logs.status`, `call_logs.source` | ค่าซ้ำเยอะ (3 ค่า) — index เดี่ยวไม่ช่วย |
| `call_logs.phone_number` | cardinality สูงแต่ **ไม่มี API ไหนค้น call_logs ด้วยเบอร์** ทำไปก็เป็นภาระ INSERT ฟรี ๆ (ตารางที่ insert บ่อยที่สุด) |
| `call_logs.risk_score` แบบเต็ม | ใช้ partial index IDX-7 แทน ได้ผลเหมือนกันแต่เล็กกว่ามาก |
| `users.created_at` | ตาราง users เล็ก (หลักพันแถว) Seq Scan เร็วพออยู่แล้ว |

## 2. ผลลัพธ์ที่วัดได้จริง

รายละเอียดเต็ม + plan ของทุก query: [`results/benchmark.md`](results/benchmark.md) และ [`results/api-latency.md`](results/api-latency.md)

**ระดับ SQL** (EXPLAIN ANALYZE, median 7 รอบ):

| Query | ไม่มี index | มี index | เร็วขึ้น | Plan (มี index) |
|---|---:|---:|---:|---|
| Call Logs ล่าสุด 20 แถว | 264 ms | 0.01 ms | ~22,000× | Index Scan, ไม่มี Sort |
| Keyset หน้าลึก 1 แสนแถว | 310 ms | 0.02 ms | ~18,000× | Index Scan |
| ประวัติการตรวจของฉัน | 116 ms | 0.02 ms | ~6,000× | Index Scan (partial IDX-8) |
| Blacklist กรอง status | 39 ms | 0.02 ms | ~2,000× | Index Scan (IDX-2) |
| สายเสี่ยงสูงวันนี้ | 133 ms | 0.20 ms | ~650× | Index Only Scan (partial IDX-7) |
| ลบเบอร์ (CASCADE reports) | 42 ms | 0.22 ms | ~190× | trigger ใช้ IDX-4 |
| จำนวนสายวันนี้ | 136 ms | 1.5 ms | ~90× | Index Only Scan (IDX-6) |

**ระดับ API จริง** (FastAPI + SQLAlchemy, header `X-Response-Time-ms`):
`/calls/stats` 246 → 8 ms (31×) · `/calls/logs` 140 → 5 ms (31×) · `/calls/trend` 134 → 12 ms (11×) · `/reports/me` 75 → 9 ms (9×)

**ต้นทุน** (lab 02, 03): index เพื่อ performance ใช้พื้นที่เพิ่ม ~210 MB (index รวม 145 → 356 MB) บนข้อมูลตาราง ~315 MB และ INSERT call_logs 200,000 แถวช้าลงจาก ~610 ms → ~960 ms (1.6×) — คุ้มเพราะระบบ "อ่าน" (dashboard ทุกครั้งที่เปิด) บ่อยกว่า "เขียน" มาก

## 3. ปรับโค้ดให้ใช้ index ได้จริง (ไม่ใช่แค่สร้าง index)

| ปัญหา | ในโค้ด (`backend/app/...`) |
|---|---|
| ❌ `WHERE date(created_at) = today` ครอบ column ด้วย function → Seq Scan (lab 04 ข้อ 4.1: 346 ms vs 5 ms) | `routers/calls.py` คำนวณ "เที่ยงคืนเวลาไทย" ใน Python แล้วส่ง `created_at >= :start` |
| partial index ใช้ได้เมื่อ WHERE "อยู่ใน" predicate เท่านั้น (`>= 79` ใช้ไม่ได้) | `risk_score >= literal_column("80")` + ค่าคงที่ `HIGH_RISK_THRESHOLD` ผูกกับ index (ห้ามตั้งผ่าน env) |
| OFFSET ลึก = อ่านแล้วทิ้ง (lab 04 ข้อ 4.5) | `GET /calls/logs` ใช้ keyset `before_id` + ไม่ `COUNT(*)` 2 ล้านแถว |
| N+1 query (ดึง report 50 รายการ แล้วไปดึงผู้แจ้ง/หมวดทีละรายการ = 101 query) | `joinedload` / `selectinload` ใน `routers/detect.py` — มี test ยืนยันจำนวน query คงที่ (`tests/test_integration.py::test_no_n_plus_one_*`) |
| `LIKE '%xxx'` ใช้ index ไม่ได้ / wildcard injection | ช่องค้นหารับเฉพาะตัวเลขแล้วต่อ `%` ท้ายเท่านั้น (`validate_phone_prefix`) |
| เก็บเบอร์หลายรูปแบบ (`081-234-5678`, `+66...`) ทำให้ค้นด้วย `=` ไม่เจอ | normalize เป็น `0812345678` ตั้งแต่ validation layer (`core/validators.py`) |
| `report_count = report_count + 1` แบบอ่าน-แก้-เขียนใน Python เสี่ยง lost update | เขียนเป็น SQL expression (atomic) ใน `_upsert_blacklist` |

## 4. ใช้กับระบบจริง

Index ทั้งหมดอยู่ใน **Alembic migration `backend/alembic/versions/0002_performance_indexes.py`** (และประกาศใน model ด้วย ให้ `alembic check` ตรงกัน) — ตอน backend container สตาร์ทจะรัน `alembic upgrade head` ให้อัตโนมัติ

- สร้างด้วย `CREATE INDEX CONCURRENTLY` → ใส่ลงฐานข้อมูลที่มีข้อมูลอยู่แล้วได้โดยไม่ lock ตาราง
- อยากเทียบก่อน/หลังบนเครื่องตัวเอง: `alembic downgrade 0001` (ลบ index) → `alembic upgrade head` (สร้างกลับ)

## ปิด / รีเซ็ต

```bash
docker compose down        # ปิด เก็บข้อมูลไว้
docker compose down -v     # ลบข้อมูลทั้งหมด (ครั้งหน้าจะ seed ใหม่)
```
