# ผล Benchmark: query จริงของ VoiceGuard API — มี index vs ไม่มี index

- วันที่วัด: 2026-10-02 23:05  |  PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
- ข้อมูล: call_logs 2,000,000 · reports 600,000 · report_categories ~860,000 · blacklist_numbers 200,000 · users 1,000
- เวลา = median ของ 7 รอบ (Execution Time จาก EXPLAIN ANALYZE, หน่วย ms) หลังวอร์มอัป 1 รอบ
- ตัวเลขขึ้นกับเครื่อง ให้ดู "อัตราส่วน" และ "plan" เป็นหลัก

| # | Endpoint | Query | Index ที่ออกแบบไว้ | ไม่มี index (ms) | มี index (ms) | เร็วขึ้น |
|---|---|---|---|---:|---:|---:|
| Q1 | `POST /detect/number` | ค้นเบอร์ตรงตัว | IDX-1 (มีทั้ง 2 DB) | 0.01 | 0.01 | 1.1× |
| Q2 | `GET /blacklist?q=` | ค้นเบอร์ขึ้นต้นด้วย (prefix) | IDX-1 (มีทั้ง 2 DB) | 0.05 | 0.06 | 0.9× |
| Q3 | `GET /blacklist?status=high_risk` | กรองสถานะ + เรียงตาม risk หน้าแรก | IDX-2 | 38.70 | 0.02 | **2,037×** |
| Q4 | `GET /blacklist` | ทั้งหมด เรียงตาม risk หน้าแรก | IDX-3 | 37.92 | 0.02 | **2,370×** |
| Q5 | `GET /blacklist/{phone}` | report ล่าสุดของเบอร์ | IDX-4 | 47.28 | 0.03 | **1,689×** |
| Q6 | `GET /reports/me` | report ของฉัน หน้าแรก | IDX-5 | 51.61 | 0.03 | **1,665×** |
| Q7 | `GET /reports/me` | นับ report ของฉัน (total) | IDX-5 | 50.43 | 0.24 | **210×** |
| Q8 | `GET /calls/stats` | จำนวนสายวันนี้ | IDX-6 | 136 | 1.46 | **93×** |
| Q9 | `GET /calls/stats` | สายเสี่ยงสูงวันนี้ | IDX-7 partial | 133 | 0.20 | **649×** |
| Q10 | `GET /calls/trend` | สายเสี่ยงสูงรายวัน 7 วัน | IDX-7 partial | 123 | 3.47 | **36×** |
| Q11 | `GET /calls/logs` | Call Logs ล่าสุด 20 แถว | IDX-6 | 264 | 0.01 | **21,999×** |
| Q12 | `GET /calls/logs?before_id=` | หน้าถัดไปแบบ keyset (ลึก ~1 แสนแถว) | IDX-6 | 310 | 0.02 | **18,246×** |
| Q13 | `GET /calls/logs?mine=true` | ประวัติการตรวจของฉัน | IDX-8 partial | 116 | 0.02 | **6,117×** |
| Q14 | `GET /contacts` | ผู้ติดต่อฉุกเฉินของฉัน | IDX-9 | 0.10 | 0.01 | **7×** |
| Q15 | `(สถิติ)` | จำนวน report ตามหมวด (M-N ค้นกลับ) | ix_report_categories_category | 55.96 | 10.76 | **5×** |
| Q16 | `DELETE /blacklist/{phone}` | ลบเบอร์ -> CASCADE ลบ reports | IDX-4 (FK) | 41.61 | 0.22 | **191×** |
| Q17 | `DELETE /users/{id}` | ลบ user -> SET NULL ใน reports/call_logs + CASCADE contacts | IDX-5, IDX-8, IDX-9 (FK) | 215 | 21.43 | **10×** |

## Plan ที่ได้ (node ที่อ่านข้อมูล/เรียงข้อมูล)

| # | ไม่มี index | มี index |
|---|---|---|
| Q1 | Index Scan (uq_blacklist_numbers_phone) | Index Scan (uq_blacklist_numbers_phone) |
| Q2 | Sort → Index Scan (uq_blacklist_numbers_phone) | Sort → Index Scan (uq_blacklist_numbers_phone) |
| Q3 | Sort → Seq Scan | Index Scan (ix_blacklist_numbers_status_risk) |
| Q4 | Sort → Seq Scan | Index Scan (ix_blacklist_numbers_risk) |
| Q5 | Sort → Seq Scan | Sort → Bitmap Heap Scan → Bitmap Index Scan (ix_reports_blacklist_created) |
| Q6 | Sort → Seq Scan | Index Scan (ix_reports_reporter_created) |
| Q7 | Seq Scan | Index Only Scan (ix_reports_reporter_created) |
| Q8 | Seq Scan | Index Only Scan (ix_call_logs_created) |
| Q9 | Seq Scan | Index Only Scan (ix_call_logs_high_risk_created) |
| Q10 | Sort → Seq Scan | Index Only Scan (ix_call_logs_high_risk_created) |
| Q11 | Sort → Seq Scan | Index Scan (ix_call_logs_created) |
| Q12 | Sort → Seq Scan | Index Scan (ix_call_logs_created) |
| Q13 | Sort → Seq Scan | Index Scan (ix_call_logs_user_created) |
| Q14 | Sort → Seq Scan | Sort → Bitmap Heap Scan → Bitmap Index Scan (ix_emergency_contacts_user) |
| Q15 | Seq Scan | Index Only Scan (ix_report_categories_category) |
| Q16 | Index Scan (blacklist_numbers_pkey) | Index Scan (blacklist_numbers_pkey) |
| Q17 | Index Scan (users_pkey) | Index Scan (users_pkey) |
