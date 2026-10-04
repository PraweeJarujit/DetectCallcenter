# VoiceGuard Threat Report: Storytelling Dashboard

Dashboard เชิงเล่าเรื่องสำหรับ **พันธมิตรของ VoiceGuard AI** (ธนาคาร, Telco, หน่วยงานรัฐ ตาม `UserRole` ในระบบ)
สรุปสิ่งที่ระบบตรวจพบตลอด 6 เดือน (1 เม.ย. – 30 ก.ย. 2026) และสิ่งที่แต่ละฝ่ายควรทำต่อ

**เปิดดู:** ดับเบิลคลิก `dashboard/index.html` (ไฟล์เดียว ไม่ต้องรันเซิร์ฟเวอร์ ไม่ต้องติดตั้งอะไร)

## เรื่องที่เล่า (7 บท)

| บท | คำถาม | ข้อค้นพบหลัก | ตารางที่ใช้ |
|---|---|---|---|
| 1 ปริมาณ | ภัยมากขึ้นไหม | การตรวจ/วันเพิ่ม 2.4 เท่า, สายเสี่ยงสูง 17.5% → 27.5% | `call_logs` |
| 2 เสียง AI | อันตรายแบบไหนโตเร็วสุด | เสียงสังเคราะห์ในสายเสี่ยงสูง 16.1% → 50.8%, “เสียงโคลน” อันดับ 5 → 1 | `call_logs`, `reports` × `scam_categories` (M-N) |
| 3 เวลาเสี่ยง | โทรมาเมื่อไหร่ | 66.2% เกิด จ.–ศ. 09–17 น., พีค 10:00 และ 14:00 | `call_logs` |
| 4 เบอร์ซ้ำ | ควรปิดเบอร์ไหนก่อน | เบอร์ 10% แรกก่อสายเสี่ยงสูง 51.4% | `call_logs`, `blacklist_numbers` |
| 5 พันธมิตร | การแจ้งเบาะแสช่วยไหม | เวลาถึง blacklist 44.6 → 14.3 ชม. (เร็วขึ้น 3.1 เท่า) | `reports` × `users`, `blacklist_numbers` |
| 6 มูลค่า | คุ้มแค่ไหน | ประมาณการ ฿4.1 ล้าน (ปรับสมมติฐานได้ด้วย slider) | `call_logs` + ค่าเฉลี่ย GASA |
| 7 ข้อเสนอ | ทำอะไรต่อ | ข้อเสนอแยกตามธนาคาร / Telco / รัฐ | — |

ส่วนหัวมีแถบ **บริบทจากสถิติจริง** ของประเทศไทย (ดูแหล่งอ้างอิงท้ายไฟล์)
ตัวกรองช่วงเวลา (6 เดือน / 90 วัน / 30 วัน) เปลี่ยน KPI, กราฟรายวัน และมูลค่าประมาณการ ทุกกราฟชี้ดูค่า (tooltip) ได้ รองรับมือถือและโหมดมืด

## ข้อมูลที่ใช้

> ⚠️ ข้อมูลระบบ (บทที่ 1–6) เป็น **ข้อมูลจำลอง** เพราะระบบยังไม่มีผู้ใช้จริง
> สร้างด้วย seed คงที่ (รันซ้ำได้ผลเดิมทุกครั้ง) และมีโครงสร้าง **ตรงกับตารางจริงใน `backend/app/models/` ทุกคอลัมน์**

```
dashboard/
├── index.html                    ← dashboard (ไฟล์เดียว ฝังข้อมูลสรุปไว้แล้ว)
├── data/
│   ├── raw/                      ← ข้อมูลดิบ 1 ไฟล์ต่อ 1 ตาราง (โหลดเข้า PostgreSQL ได้)
│   │   ├── call_logs.csv             68,124 แถว
│   │   ├── blacklist_numbers.csv      1,654 แถว
│   │   ├── reports.csv                4,019 แถว
│   │   ├── report_categories.csv      4,994 แถว (M-N)
│   │   ├── scam_categories.csv            8 แถว
│   │   ├── users.csv                     36 แถว (ไม่มีรหัสผ่าน)
│   │   └── emergency_contacts.csv        35 แถว
│   └── aggregated/               ← ตารางสรุปที่แต่ละกราฟใช้ + dashboard_data.json
├── sql/
│   ├── load_data.sql             ← \copy ข้อมูลดิบเข้า PostgreSQL
│   └── queries.sql               ← SQL ที่ให้ผลเดียวกับไฟล์ aggregated (1 query ต่อ 1 กราฟ)
├── scripts/
│   ├── generate_data.py          ← สร้างข้อมูลดิบ (สมมติฐานเขียนไว้หัวไฟล์)
│   ├── build_aggregates.py       ← raw → aggregated
│   └── build_dashboard.py        ← ฝัง JSON ลง template → index.html
└── src/template.html             ← ต้นฉบับ dashboard (HTML/CSS/JS ล้วน ไม่ใช้ library)
```

### Data dictionary (คอลัมน์หลัก)

| ตาราง | คอลัมน์ | ความหมาย |
|---|---|---|
| `call_logs` | `risk_score` 0–100, `status` | ≥ 80 = `high_risk`, 50–79 = `suspect`, < 50 = `safe` (ตรง `HIGH_RISK_THRESHOLD`) |
| | `is_synthetic_voice` | ตรวจพบเสียงสังเคราะห์ (เป็นไปได้เฉพาะ `source` = `audio` / `demo`) |
| | `source` | `number_check` ตรวจเบอร์, `audio` วิเคราะห์ไฟล์เสียง, `demo` หน้า Call Demo |
| | `user_id` | ว่าง = ผู้ใช้ไม่ login |
| `blacklist_numbers` | `report_count`, `risk_score` | ค่าสรุปจาก `reports` ของเบอร์นั้น |
| | `first_reported_at` | ใช้คำนวณ “เวลาจากสายแรกถึง blacklist” เทียบกับ `min(call_logs.created_at)` |
| `reports` | `reported_by` | FK → `users` (ว่าง = ไม่ระบุผู้แจ้ง) |
| `report_categories` | `report_id`, `category_id` | M-N ระหว่าง `reports` และ `scam_categories` |
| `users` | `role` | `bank` / `telco` / `gov` / `admin` |

เวลาทั้งหมดเป็น ISO 8601 พร้อม timezone `+07:00`

## สร้างใหม่ / โหลดเข้าฐานข้อมูล

```bash
# สร้างข้อมูลและ dashboard ใหม่ทั้งหมด (Python 3.10+, standard library ล้วน)
python dashboard/scripts/generate_data.py
python dashboard/scripts/build_aggregates.py
python dashboard/scripts/build_dashboard.py

# โหลดเข้า PostgreSQL ของระบบ (ฐานข้อมูลว่างที่ alembic upgrade head แล้ว)
psql "$DATABASE_URL" -f dashboard/sql/load_data.sql
psql "$DATABASE_URL" -f dashboard/sql/queries.sql
```

## แหล่งอ้างอิงสถิติจริง (แถบบริบท)

- [Thai Examiner, 19 มี.ค. 2026](https://www.thaiexaminer.com/thai-news-foreigners/2026/03/19/scam-threat-again-on-the-rise-in-thailand-with-losses-of-70-million-baht-a-day-being-reported-by-police/): ความเสียหาย 2025 ฿115.3 พันล้าน, สายหลอก 39 ล้านสาย, SMS 134 ล้านข้อความ
- [Thai PBS Verify](https://www.thaipbs.or.th/verify/article/content/2683): thaipoliceonline เม.ย. 2568 เฉลี่ย 960 คดี/วัน, ฿55 ล้าน/วัน
- [Nation Thailand (รายงาน GASA)](https://www.nationthailand.com/news/general/40058129): ค่าเสียหายเฉลี่ย ฿12,956 ต่อคน

## ข้อจำกัด

- ตัวเลขบทที่ 1–6 เป็นข้อมูลจำลองเพื่อสาธิตการเล่าเรื่อง ไม่ใช่สถิติจริงของระบบ
- “มูลค่าที่ป้องกันได้” เป็นการประมาณการ ต้องเก็บผลลัพธ์หลังเตือน (เช่น ผู้ใช้โอนเงินหรือไม่) ก่อนจึงวัดได้จริง
- เบอร์โทรในตารางเป็นเลขสุ่ม และแสดงผลแบบปิดเลขกลาง
