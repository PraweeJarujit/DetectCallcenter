# ผลวัดเวลาตอบสนองของ API จริง (end-to-end ผ่าน FastAPI + SQLAlchemy)

- รัน backend 2 ตัวชี้ไปที่ database มี index / ไม่มี index (ข้อมูลเดียวกัน: call_logs 2 ล้าน, reports 6 แสน)
- เวลา = median ของ header `X-Response-Time-ms` (เวลาที่ server ใช้ทั้ง request รวม JSON serialize) จาก 7 รอบ
- `/api/blacklist` แบบไม่กรองยังใช้ ~20 ms เพราะ `COUNT(*)` ทั้ง 200,000 แถวเพื่อทำตัวเลขหน้า (index ช่วยแค่ส่วน ORDER BY ... LIMIT)

| Endpoint | ไม่มี index (ms) | มี index (ms) | เร็วขึ้น |
|---|---:|---:|---:|
| `GET /api/calls/stats` | 245.6 | 7.8 | **31×** |
| `GET /api/calls/trend` | 134.0 | 11.7 | **11×** |
| `GET /api/calls/logs?limit=20` | 140.4 | 4.6 | **31×** |
| `GET /api/calls/logs?mine=true` | 96.7 | 4.7 | **21×** |
| `GET /api/blacklist?status=high_risk` | 52.8 | 11.4 | **5×** |
| `GET /api/blacklist` | 39.0 | 22.3 | **2×** |
| `GET /api/blacklist/{phone}` | 45.8 | 9.9 | **5×** |
| `GET /api/reports/me` | 74.9 | 8.6 | **9×** |

ต้นทุนฝั่งเขียน (labs/03-insert-cost.sql — INSERT call_logs 200,000 แถว): ไม่มี index ≈ 610 ms · มี index ≈ 960 ms (ช้าลง ~1.6 เท่า แลกกับ dashboard ที่เร็วขึ้น 11-31 เท่า)
