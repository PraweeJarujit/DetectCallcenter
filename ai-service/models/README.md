# models/

ไฟล์โมเดลที่ใช้งานจริง สร้างโดย GitHub Actions workflow **Train AI models** (`.github/workflows/train-models.yml`)

| ไฟล์ | คืออะไร |
|---|---|
| `voice_model.joblib` | โมเดลแยกเสียงคนจริง / เสียงสังเคราะห์ |
| `voice_metrics.json` | ผลทดสอบล่าสุดของโมเดลเสียง (ข้อมูลที่โมเดลไม่เคยเห็น) |
| `text_model.joblib` | โมเดลจับข้อความหลอกลวงภาษาไทย |
| `text_metrics.json` | ผลทดสอบล่าสุดของโมเดลข้อความ |
