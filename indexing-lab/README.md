# Indexing Lab — 8903316 Web Application Development

เปรียบเทียบ PostgreSQL 2 ตัวที่มีข้อมูลเหมือนกัน 1,000,000 rows ต่างกันแค่ index

| Service | Port | หมายเหตุ |
|---|---|---|
| pg_with_index | 5432 | มี `idx_tx_date`, `idx_tx_customer` |
| pg_no_index | 5433 | มีแค่ Primary Key |
| adminer | http://localhost:8080 | GUI (System: PostgreSQL, Server: `pg_with_index` หรือ `pg_no_index`) |

User / Password / DB: `student` / `student` / `appdb`

## เริ่มต้น

```bash
docker compose up -d
docker compose logs -f pg_no_index     # รอจนเห็น ">>> Seed done" แล้ว Ctrl+C
docker compose ps                      # ทั้ง 2 ตัวต้องเป็น (healthy)
```

ครั้งแรกใช้เวลา seed ประมาณ 30-90 วินาที (ขึ้นกับเครื่อง)

## รัน lab (ใช้ได้ทั้ง PowerShell, CMD, Terminal)

```bash
docker exec -it pg_with_index psql -U student -d appdb -f /labs/01-explain.sql
docker exec -it pg_no_index   psql -U student -d appdb -f /labs/01-explain.sql
```

เปลี่ยนชื่อไฟล์ตาม lab:

| ไฟล์ | รันบน | เนื้อหา |
|---|---|---|
| 01-explain.sql | ทั้ง 2 ตัว | EXPLAIN ANALYZE 5 แบบ |
| 01b-create-index-live.sql | pg_no_index | สร้าง index เอง + Demo ลูกค้า 100 คน (ทีละ step, ต้อง DROP ท้าย) |
| 02-size.sql | ทั้ง 2 ตัว | ขนาด table vs index |
| 03-insert-cost.sql | ทั้ง 2 ตัว | INSERT 200,000 rows แล้ว ROLLBACK |
| 04-pitfalls.sql | pg_with_index | กรณีมี index แต่ไม่ถูกใช้ |
| 05-composite.sql | pg_with_index | Composite index + Leftmost rule (ROLLBACK คืนค่าเอง) |
| 06-workshop.sql | pg_with_index | โจทย์ workshop |
| 07-choose-columns.sql | pg_with_index | เลือก column / ทำไมไม่ทำทุก column |

เข้า psql แบบ interactive:

```bash
docker exec -it pg_with_index psql -U student -d appdb
```

คำสั่งที่ใช้บ่อยใน psql: `\d transactions`, `\di`, `\timing on`, `\q`

## ปิด / รีเซ็ต

```bash
docker compose down        # ปิด เก็บข้อมูลไว้
docker compose down -v     # ลบข้อมูลทั้งหมด (ครั้งหน้าจะ seed ใหม่)
```

## ใช้กับ DBeaver

สร้าง connection: localhost / port 5432 (with index) และ 5433 (no index) / appdb / student / student
ไฟล์ 01b และ 07 รันใน DBeaver ได้ทันที ไฟล์อื่นให้ลบบรรทัดที่ขึ้นต้นด้วย `\` (เช่น `\timing`, `\echo`) ก่อน
ดู plan: `Ctrl+Shift+E` ติ๊ก Analyze | รันทั้งไฟล์: `Alt+X`

## ปัญหาที่พบบ่อย

- **port 5432 is already allocated** → เครื่องมี PostgreSQL อยู่แล้ว แก้ `ports` ใน docker-compose.yml เป็น `"15432:5432"`
- **relation "transactions" does not exist** → ยัง seed ไม่เสร็จ หรือเคยรันด้วยไฟล์เก่า ให้ `docker compose down -v` แล้ว `up -d` ใหม่
- **แก้ไฟล์ใน sql/init แล้วไม่มีผล** → init script รันแค่ตอน volume ว่าง ต้อง `down -v` ก่อน
- **Mac M1/M2** → image ทั้งหมดรองรับ arm64 ใช้ได้เลย
