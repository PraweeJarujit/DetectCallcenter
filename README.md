# VoiceGuard — ตรวจเบอร์ ข้อความ และเสียงมิจฉาชีพ

เว็บสำหรับคนทั่วไปเช็กก่อนเชื่อ: ใส่เบอร์ที่โทรมา วางข้อความ SMS/LINE หรืออัปโหลดเสียงที่สงสัย แล้วได้คำตอบทันทีว่าน่าเชื่อถือแค่ไหน และควรทำอะไรต่อ

| แพ็กเกจ | ราคา | ได้อะไร |
|---|---|---|
| ฟรี | 0 บาท | ตรวจเบอร์วันละ 5 ครั้ง · ทดลองตรวจระหว่างสายวันละ ~1 นาที · ดูรายชื่อเบอร์อันตราย · แจ้งเบอร์ |
| Premium | 59 บาท/เดือน | **AI ฟังระหว่างสายแบบเรียลไทม์ไม่จำกัด** (เสียง + คำพูด) · ตรวจเบอร์ไม่จำกัด · AI ตรวจข้อความหลอกลวง · AI ตรวจเสียงสังเคราะห์ (deepfake) · แจ้งผู้ติดต่อฉุกเฉินเมื่อพบความเสี่ยงสูง · ประวัติการตรวจ |

> **การชำระเงินเป็นโหมดทดลอง** (`PAYMENT_PROVIDER=mock`) — หน้า checkout แสดง QR พร้อมเพย์จำลองและปุ่ม "จำลองการชำระเงินสำเร็จ" ยังไม่มีการตัดเงินจริง ดูหัวข้อ [ต่อระบบชำระเงินจริง](#ต่อระบบชำระเงินจริง)

## สถาปัตยกรรม

```
 browser ──► frontend (Nginx, HTML/JS ไม่มี build step)
                │  /api/*
                ▼
            backend (FastAPI + SQLAlchemy + Alembic) ──► PostgreSQL 16
                │  /analyze, /analyze-text
                ▼
            ai-service (FastAPI + scikit-learn) — โมเดลเสียง + โมเดลข้อความ
```

```
docker-compose.yml        db + ai-service + backend + frontend
render.yaml               Blueprint deploy ขึ้น Render (4 service)
.github/workflows/
  ci.yml                  test backend (PostgreSQL จริง) + ai-service + build Docker ทุก push/PR
  train-models.yml        ดาวน์โหลด dataset → เทรนโมเดล → ทดสอบ → commit โมเดลกลับเข้า branch
ai-service/
  app/                    audio.py (โหลด/ตัดเสียง) · features.py (MFCC/LFCC/spectral) · text_signals.py · main.py
  training/               prepare_voice_data.py · train_voice.py · train_text.py · thai_scam_corpus.py · augment.py
  models/                 voice_model.joblib · text_model.joblib · *_metrics.json (ผลทดสอบจริง)
backend/
  alembic/versions/       0001 schema · 0002 index · 0003 subscription + contact
  app/routers/            auth, users, detect, calls, contacts, billing
  tests/                  pytest 107 tests
frontend/
  index.html              หน้าแรก: ตรวจเบอร์ได้ทันที + ตรวจระหว่างสาย + ราคา + คำถามที่พบบ่อย + ติดต่อเรา
  pages/                  login · check · live (ตรวจระหว่างสาย) · history · numbers · account · admin
  audio/                  สายตัวอย่าง + คะแนนจริงของโมเดล (demo-calls.json)
  js/                     api.js · ui.js (shell + ไอคอน) · checker.js · history.js
db-indexing/, indexing-lab/, dashboard/   งานประกอบรายวิชา (index lab, storytelling dashboard)
```

## หน้าเว็บ

ทุกหน้าหลักอยู่ห่างกันแค่ 1 คลิกจากแถบเมนู (มือถือเป็นแถบล่าง)

| หน้า | ใช้ทำอะไร |
|---|---|
| หน้าแรก `/` | ตรวจเบอร์ได้เลยโดยไม่ต้องสมัคร · ดูแพ็กเกจ · ส่งข้อความติดต่อเรา |
| ตรวจ `pages/check.html` | ตัวตรวจ 3 แบบ (เบอร์ / ข้อความ / ไฟล์เสียงหรืออัดเสียง) + สรุปสถิติ + ตรวจล่าสุด |
| ระหว่างสาย `pages/live.html` | AI ฟังสายสด ๆ ทุก 2 วินาที (ไม่ต้อง login ก็ลองสายตัวอย่างได้) — ดูหัวข้อ [ตรวจระหว่างสาย](#ตรวจระหว่างสาย-เรียลไทม์) |
| ประวัติ `pages/history.html` | ผลตรวจทั้งหมดของตัวเอง กรองตามประเภท |
| เบอร์อันตราย `pages/numbers.html` | ค้นรายชื่อเบอร์ที่ถูกแจ้ง · ดูรายละเอียด · แจ้งเบอร์ใหม่ |
| บัญชี `pages/account.html` | สมัคร/ยกเลิก Premium · ประวัติชำระเงิน · ผู้ติดต่อฉุกเฉิน · ข้อมูลส่วนตัว |
| แอดมิน `pages/admin.html` | ภาพรวมสมาชิกและรายได้ · กล่องข้อความติดต่อเรา · จัดการเบอร์ · สมาชิกล่าสุด |

## ตรวจระหว่างสาย (เรียลไทม์)

จุดขายหลักของ VoiceGuard: เปิดหน้า **ระหว่างสาย** ไว้ขณะคุยโทรศัพท์ แล้ว AI จะฟังและเตือนทันที

| แหล่งเสียง | ใช้กับ | วิธีทำงาน |
|---|---|---|
| เปิดลำโพงให้ฟัง | สายโทรศัพท์ทั่วไป (มือถือ/คอม) | ไมโครโฟนรับเสียงจากลำโพง (ปิด noise suppression ของเบราว์เซอร์) + ถอดคำพูดภาษาไทยด้วย Web Speech API (Chrome/Edge) |
| เสียงจากคอม | LINE / Messenger / Zoom บนคอม | `getDisplayMedia` แชร์หน้าจอพร้อม "เสียงของระบบ" (Chrome/Edge บน Windows) |
| สายตัวอย่าง | นำเสนอ / ทดลอง | เล่นไฟล์เสียงจริงใน `frontend/audio/` ผ่านระบบเดียวกัน คำบรรยายจากสคริปต์ |

```
เสียง -> AudioWorklet (js/pcm-capture.js) -> ลดเป็น 16 kHz mono -> ring buffer 4 วินาที
     -> ทุก 2 วินาที: ช่วงที่มีเสียงพูด >= 20% ส่ง WAV ไป POST /api/live/chunk -> ai-service /analyze
     -> เกจ = ค่าเฉลี่ยเคลื่อนที่ (EMA) · แถบเส้นเวลา 1 แท่ง/2 วินาที · เตือนเมื่อ EMA >= 0.7 ติดกัน 3 ช่วงขึ้นไป
คำพูด -> POST /api/live/text (Premium) -> สัญญาณเตือน + ไฮไลต์คำในบทสนทนา
จบสาย -> POST /api/live/summary -> บันทึกประวัติ 1 แถว + แจ้งผู้ติดต่อฉุกเฉิน (Premium, คะแนน >= 80)
```

ข้อจำกัด: เว็บดักเสียงจากสายโทรศัพท์มือถือโดยตรงไม่ได้ (iOS/Android ไม่อนุญาต) จึงใช้วิธีเปิดลำโพง ถ้าจะดักสายโดยตรงต้องทำเป็นแอปมือถือ (Android `CallScreeningService` + อัดเสียงผ่านลำโพง หรือ VoIP ของตัวเอง)

สายตัวอย่างสร้างโดย `ai-service/training/make_demo_calls.py` (รันอัตโนมัติท้าย workflow Train AI models): มิจฉาชีพอ้างเป็นตำรวจอ่านด้วย edge-tts และเสียงคนไทยจริงจาก FLEURS split test (ผู้พูดที่โมเดลไม่เคยได้ยิน) ผ่านสายโทรศัพท์จำลองเหมือนกัน คะแนนทีละช่วงของโมเดลจริงเก็บใน `frontend/audio/demo-calls.json` และหน้าแรกวาดกราฟจากไฟล์นี้

ผลตรวจแสดงเป็น "ใบผล" ที่บอกระดับความเสี่ยง เหตุผล (เช่น สัญญาณ "ขอให้โอนเงิน", "อ้างเป็นเจ้าหน้าที่รัฐ" พร้อมคำที่เจอ) และขั้นตอนถัดไป เช่น โทร 1441 หรือแจ้งเบอร์นี้

## โมเดล AI

โมเดลทั้งสองตัวเทรนบน GitHub Actions (`train-models.yml`) จาก dataset สาธารณะ แล้ว commit ไฟล์โมเดลกลับเข้า repo ผลทดสอบล่าสุดอยู่ใน `ai-service/models/voice_metrics.json` และ `text_metrics.json` และหน้าเว็บแสดงตัวเลขนี้ใต้ผลตรวจ (ผ่าน `/api/ai/status`)

### ตรวจเสียงสังเคราะห์ (voice deepfake)

- **ข้อมูลเทรน**
  - [In-the-Wild](https://huggingface.co/datasets/mueller91/In-The-Wild) — เสียงคนดังจริงกับ deepfake ที่หลุดออกมาในโลกจริง (อังกฤษ) แบ่ง train/test ตามตัวผู้พูด ไม่ให้คนเดียวกันอยู่ทั้งสองฝั่ง
  - [Google FLEURS](https://huggingface.co/datasets/google/fleurs) ภาษาไทย (`th_th`) — เสียงคนไทยจริง
  - เสียงสังเคราะห์ภาษาไทยที่สร้างเองจากประโยค FLEURS ด้วย edge-tts (Microsoft Neural 3 เสียง) และ gTTS — เพิ่ม [MMS-TTS ไทย](https://huggingface.co/facebook/mms-tts-tha) ของ Meta ได้ตอนกดรัน workflow เอง (เลือก `with_mms`)
  - augment ทั้งเสียงจริงและเสียงปลอมเหมือนกัน (เสียงรบกวน, ช่องสัญญาณโทรศัพท์ 8 kHz, เสียงก้อง) เพื่อไม่ให้โมเดลจำ "คุณภาพไฟล์" แทนที่จะจำ "เสียงสังเคราะห์"
- **โมเดล**: ตัดเสียงเป็นช่วง 4 วินาที → MFCC + LFCC + delta + spectral/LTAS (numpy/scipy) → HistGradientBoosting หรือ LogisticRegression (เลือกตัวที่ดีกว่าบนชุดทดสอบ) → คะแนนรวมจากค่าเฉลี่ยครึ่งบนของทุกช่วง
- **ผลทดสอบ** (ชุดทดสอบที่ไม่เคยเห็นตอนเทรน): 

  | ชุดทดสอบ | จำนวนคลิป | แม่นยำ | AUC | เสียงจริงที่ผ่าน | เสียงปลอมที่จับได้ |
  |---|---:|---:|---:|---:|---:|
  | รวม (เสียงชัด) | 1,709 | 98.6% | 0.999 | 98.3% | 98.8% |
  | รวม (ผ่านช่องสัญญาณโทรศัพท์) | 1,709 | 97.4% | 0.997 | 95.8% | 98.6% |
  | In-the-Wild (ผู้พูดที่ไม่เคยเห็น) | 1,204 | 98.0% | 0.997 | 97.3% | 98.5% |
  | ภาษาไทย (ประโยคที่ไม่เคยเห็น) | 505 | 100% | 1.000 | 100% | 100% |

  ข้อมูลเทรน: In-the-Wild 4,000 + 4,000 คลิป · เสียงไทยจริง 1,460 คลิป · เสียงไทยสังเคราะห์ 1,030 คลิป (edge-tts 532, gTTS 498) — ตัวเลขภาษาไทย 100% บอกได้แค่ว่าแยกเสียง TTS ทั่วไปออกจากเสียงคนได้ ยังไม่ใช่หลักฐานว่าจับเสียง clone ภาษาไทยได้

### ตรวจข้อความหลอกลวงภาษาไทย

- **ข้อมูลเทรน**: ชุดข้อความหลอกลวงกึ่งสังเคราะห์ 13 รูปแบบที่พบบ่อยในไทย (อ้างตำรวจ/DSI, พัสดุตกค้าง, การไฟฟ้า, เงินกู้, งานออนไลน์, ลงทุน, รางวัล ฯลฯ — แนวการแบ่งประเภทอ้างอิงจากงาน [ThaiScamBench (KMITL)](https://dspace.kmitl.ac.th/handle/123456789/20335)) + ข้อความปกติที่ใกล้เคียง (OTP จริงจากธนาคาร, แจ้งพัสดุจริง) + ข้อความทั่วไปจาก [wisesight-sentiment](https://huggingface.co/datasets/pythainlp/wisesight_sentiment)
- **โมเดล**: TF-IDF ตัวอักษร 2-5 gram + LogisticRegression และกฎสัญญาณเตือน 11 แบบที่อธิบายให้ผู้ใช้เห็นว่าทำไมน่าสงสัย
- **ผลทดสอบ**: 

  | ชุดทดสอบ | จำนวน | แม่นยำ | precision | recall | AUC |
  |---|---:|---:|---:|---:|---:|
  | แม่แบบที่ไม่เคยเห็นตอนเทรน | 2,847 | 98.4% | 97.6% | 97.0% | 0.998 |
  | ข้อความที่เขียนด้วยมือแยกต่างหาก | 48 | 93.8% | 95.7% | 91.7% | 0.997 |

  เตือนผิดกับข้อความโซเชียลทั่วไปที่ไม่ได้ใช้เทรน (wisesight 3,000 ข้อความ): 0.17% · ข้อมูลเทรน: แม่แบบ 5,516 ข้อความ + wisesight 6,000 ข้อความ (น้ำหนัก 0.3)

### ข้อจำกัดที่ควรรู้

- เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่คำตัดสิน — ผล "ไม่พบสัญญาณอันตราย" ไม่ได้แปลว่าปลอดภัย 100%
- เสียงปลอมภาษาไทยในชุดเทรนมาจาก TTS 2 ตระกูล เสียง clone จากเครื่องมืออื่นอาจหลุดได้ ควรเติมตัวอย่างจริงเมื่อมี
- ข้อความหลอกลวงส่วนใหญ่สร้างจากแม่แบบ ตัวเลข held-out จึงวัดจาก **แม่แบบที่โมเดลไม่เคยเห็น** และชุดข้อความที่เขียนด้วยมือแยกต่างหาก (`training/eval_texts_th.jsonl`)
- ใบอนุญาตข้อมูล: MMS-TTS เป็น CC-BY-NC 4.0 จึงปิดไว้เป็นค่าเริ่มต้น (โมเดลที่ใช้อยู่ไม่ได้เทรนด้วย MMS) · In-the-Wild และ FLEURS ใช้เพื่อการวิจัย/การศึกษา

### เทรนใหม่

GitHub → Actions → **Train AI models** → Run workflow (ปรับจำนวนตัวอย่างได้) หรือรันเองในเครื่อง:

```bash
cd ai-service
pip install -r requirements.txt -r requirements-train.txt
python -m training.train_text
python -m training.prepare_voice_data --itw-zip release_in_the_wild.zip --out data/voice --itw-per-class 4000 --thai-fake 1500   # เพิ่ม --with-mms ได้
python -m training.train_voice --manifest data/voice/manifest.csv
```

## รันในเครื่อง

```bash
cp backend/.env.example backend/.env      # แก้ POSTGRES_PASSWORD, DATABASE_URL และ JWT_SECRET_KEY (openssl rand -hex 32)
docker compose up -d --build
docker compose ps                         # db / voiceguard-ai / backend / frontend ต้องเป็น healthy
```

| | URL |
|---|---|
| หน้าเว็บ | http://localhost:3000 |
| Swagger UI | http://localhost:8000/docs |
| AI service | http://localhost:9000/health |
| PostgreSQL | localhost:5434 |

บัญชีทดลอง (สร้างเมื่อ `SEED_DEMO_DATA=true`) — หน้าเข้าสู่ระบบมีปุ่มกดเข้าได้ทันที

| ชื่อผู้ใช้ | รหัสผ่าน | สถานะ |
|---|---|---|
| `demo` | `demo1234` | Premium (มีผู้ติดต่อฉุกเฉิน 2 คน) |
| `free.demo` | `demo1234` | ฟรี |
| `admin` | `Admin1234` | ผู้ดูแลระบบ |

## Testing

ต้องใช้ Python 3.12

```bash
cd backend && pip install -r requirements-dev.txt && pytest          # 107 tests, coverage ≥ 70% (ได้ ~98%)
cd ai-service && pip install -r requirements-dev.txt && pytest       # 14 tests, coverage ≥ 80% (ได้ ~93%)
```

backend test ใช้ SQLite ชั่วคราวเป็นค่าเริ่มต้น ตั้ง `TEST_DATABASE_URL` เพื่อรันบน PostgreSQL จริง (ใช้ฐานข้อมูลแยก เพราะ test ล้างทุกตาราง)

| ไฟล์ test | ทดสอบอะไร |
|---|---|
| `test_live.py` | โควตาทดลองฟรี (ตาม IP / บัญชี), Premium ไม่จำกัด, AI ล่มไม่หักสิทธิ์, คำพูด (Premium, ไม่บันทึก), สรุปผล + แจ้งผู้ติดต่อ |
| `test_billing.py` | แพ็กเกจ, checkout, ยืนยันชำระเงินจำลอง, ต่ออายุ, หมดเวลา, ยกเลิก, ติดต่อเรา, หน้าแอดมิน |
| `test_detect.py` | โควตาตรวจเบอร์ฟรี, ข้อความ/เสียงต้องเป็น Premium (402), AI ล่ม (503), แจ้งผู้ติดต่อฉุกเฉิน, blacklist CRUD |
| `test_auth.py` · `test_users.py` | สมัคร, login, rate limit, logout revoke token, สิทธิ์ member/admin |
| `test_calls.py` · `test_contacts.py` | ประวัติเห็นเฉพาะของตัวเอง, keyset pagination, CRUD ผู้ติดต่อ + กัน IDOR |
| `test_integration.py` | flow ตั้งแต่สมัครถึง logout, รูปแบบ error, security headers, CORS, ไม่มี N+1 |
| `ai-service/tests/test_ai.py` | โหลดเสียงหลายรูปแบบ, feature, `/analyze`, `/analyze-text`, ไฟล์เสีย/สั้นเกิน, ไม่มีโมเดล |

## CI/CD (GitHub Actions)

| Workflow | ทำงานเมื่อ | ทำอะไร |
|---|---|---|
| `ci.yml` | push / pull request | backend: `alembic upgrade head` + `alembic check` + seed + pytest บน PostgreSQL 16 · ai-service: ruff + pytest + ทดสอบโหลดโมเดลจริง · build Docker image ทั้งสองตัว |
| `train-models.yml` | แก้โค้ดเทรน/feature หรือกดรันเอง | ดาวน์โหลด dataset → เทรน → pytest กับโมเดลใหม่ → สรุปผลใน job summary → commit โมเดลกลับเข้า branch |

แนะนำให้ตั้ง branch protection ของ `main`: Settings → Branches → Require a pull request + Require status checks (`backend`, `ai-service`, `docker`) ก่อน merge

## API หลัก

| Method | Path | สิทธิ์ | หมายเหตุ |
|---|---|---|---|
| POST | `/api/register`, `/api/login`, `/api/logout`, `/api/change-password` | - / - / login / login | login ผิดเกิน 5 ครั้ง/นาที → 429 |
| POST | `/api/detect/number` | - | ไม่ login = วันละ 5 ครั้งต่อ IP · ฟรี = วันละ 5 ครั้ง · Premium ไม่จำกัด (เกิน → 429 `QUOTA_EXCEEDED`) |
| POST | `/api/detect/text` | Premium | AI ข้อความ + สัญญาณเตือน |
| POST | `/api/detect/audio` | Premium | AI เสียง (wav/mp3/m4a/ogg/webm ≤ 10 MB) |
| POST | `/api/live/chunk` · GET `/api/live/quota` | - | ตรวจระหว่างสาย ช่วงละ ~4 วินาที · ฟรีวันละ 30 ช่วง Premium ไม่จำกัด |
| POST | `/api/live/text` · `/api/live/summary` | Premium / - | คำพูดระหว่างสาย (ไม่บันทึกทุกครั้ง) · สรุปผลตอนจบสาย |
| GET | `/api/billing/plans` · `/api/billing/me` · `/api/billing/payments` | - / login / login | |
| POST | `/api/billing/checkout` · `/api/billing/checkout/{id}/confirm` · `/api/billing/cancel` | login | confirm ใช้ได้เฉพาะโหมด mock |
| GET | `/api/me/summary` · `/api/ai/status` | login / - | สถิติของฉัน · สถานะและความแม่นยำของโมเดล |
| POST | `/api/contact` | - | จำกัด 5 ข้อความ/ชั่วโมงต่อ IP |
| GET/PUT | `/api/admin/contact-messages` · GET `/api/admin/overview` | admin | |
| GET | `/api/blacklist?q=&status=&page=` · `/api/blacklist/{phone}` | - / login | |
| POST/PUT/DELETE | `/api/blacklist`, `/api/blacklist/{phone}` | admin | |
| POST | `/api/report` · GET `/api/reports/me` · `/api/categories` | login / login / - | แจ้งเบอร์ เลือกได้หลายหมวด |
| GET | `/api/calls/logs?before_id=` | login | สมาชิกเห็นเฉพาะของตัวเอง admin เห็นทั้งหมด |
| GET/POST/PUT/DELETE | `/api/contacts`, `/api/contacts/{id}` | login | ผู้ติดต่อฉุกเฉิน |

ทุก error ตอบรูปแบบเดียวกัน:

```json
{"success": false,
 "error": {"code": "PREMIUM_REQUIRED", "message": "ฟีเจอร์นี้สำหรับสมาชิก Premium (59 บาท/เดือน)", "details": null},
 "request_id": "3f2a9c1d0b7e4a51"}
```

## Security

- XSS: escape ทุกค่าก่อนใส่ `innerHTML` + CSP · CSRF: JWT ใน header ไม่ใช้ cookie · CORS จำกัด origin
- bcrypt · JWT มี `jti` และ revoke ตอน logout · rate limit login / ตรวจเบอร์ / ติดต่อเรา · สมัครเป็น admin เองไม่ได้
- ดูข้อมูล การชำระเงิน และประวัติของคนอื่นไม่ได้ (ตอบ 404 กัน IDOR) · redirect หลัง login อนุญาตเฉพาะหน้าภายในเว็บ
- secret อยู่ใน env · production ไม่ยอมสตาร์ทถ้าใช้ secret ตัวอย่าง · container รันด้วย non-root · DB bind เฉพาะ 127.0.0.1
- ไม่เก็บตัวข้อความหรือไฟล์เสียงที่ผู้ใช้ส่งมาตรวจ เก็บเฉพาะผลตรวจ

## Deploy ขึ้น Render

1. Render Dashboard → New → Blueprint → เลือก repo นี้ → Render สร้าง PostgreSQL + `voiceguard-ai` + `voiceguard-api` + `voiceguard-web`
2. แก้ใน `render.yaml` ให้ตรงกับ URL จริง: `CORS_ORIGINS`, `VOICEGUARD_AI_URL` และปลายทาง rewrite `/api/*`
3. ระบบจริงตั้ง `SEED_DEMO_DATA=false` แล้วสร้าง admin เอง

free plan จะหลับเมื่อไม่มีคนใช้ ครั้งแรกที่ตรวจเสียงหรือข้อความอาจรอ ~1 นาที (`AI_TIMEOUT_SECONDS=60`)

## ต่อระบบชำระเงินจริง

โค้ดแยกขั้นตอนไว้แล้ว: `POST /billing/checkout` สร้างรายการ `payments` สถานะ `pending` พร้อมเลขอ้างอิง ส่วนการเปิดสิทธิ์อยู่ในฟังก์ชันเดียวกับ `confirm` เมื่อจะใช้จริง

1. เลือกผู้ให้บริการที่รองรับพร้อมเพย์ + บัตร (เช่น Omise/Opn, GB Prime Pay, Stripe Thailand)
2. ให้ `checkout` เรียก API ของผู้ให้บริการ เก็บ charge id ใน `provider_ref` แล้วส่ง QR/ลิงก์จริงกลับไป
3. เพิ่ม endpoint webhook ที่ตรวจลายเซ็นของผู้ให้บริการ แล้วเปิดสิทธิ์ Premium เหมือน `confirm`
4. ตั้ง `PAYMENT_PROVIDER` เป็นชื่อผู้ให้บริการ — endpoint `confirm` จะปิดเองอัตโนมัติ
5. ต่ออายุรายเดือนอัตโนมัติต้องใช้ระบบ subscription/recurring ของผู้ให้บริการ (ตอนนี้ `auto_renew` เป็นแค่ธง)

## หมายเหตุ

- เปลี่ยน schema: แก้ model → `alembic revision --autogenerate -m "..."` → ตรวจไฟล์ → `alembic upgrade head` (`alembic check` ใน CI ยืนยันว่า model กับ migration ตรงกัน)
- การแจ้งผู้ติดต่อฉุกเฉินตอนนี้เป็นการจำลอง (บันทึก log ไม่ส่ง SMS จริง) — ต่อผู้ให้บริการ SMS ได้ที่ `_alert_contacts` ใน `backend/app/routers/detect.py`
- index lab และผลวัด performance ดู [`db-indexing/`](db-indexing/README.md) · dashboard สำหรับนำเสนอดู [`dashboard/`](dashboard/README.md)
