"""
ตั้งค่าแอปทั้งหมดแบบรวมศูนย์ อ่านค่าจาก environment variables / .env
ใช้ pydantic-settings เพื่อ validate ค่าตั้งแต่ตอน startup (fail fast ถ้าลืมตั้งค่า secret)
"""
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET = "CHANGE_ME_IN_PRODUCTION"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "DetectCallcenter API"
    # development | test | production  — production จะบังคับตรวจ secret/CORS เข้มขึ้น
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+psycopg2://dcc_user:dcc_password@db:5432/detectcallcenter"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    # log SQL ทุกคำสั่ง (ใช้ debug ปัญหา N+1) — อย่าเปิดใน production
    DB_ECHO: bool = False

    JWT_SECRET_KEY: str = INSECURE_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # รายชื่อ origin ที่อนุญาตให้เรียก API ข้ามโดเมน คั่นด้วย comma
    # เช่น "https://voiceguard.onrender.com,http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # กัน brute-force: login ผิดได้กี่ครั้งต่อหน้าต่างเวลา (ต่อ IP + username)
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECONDS: int = 60

    VOICEGUARD_AI_URL: str = "http://voiceguard-ai:9000"
    MAX_AUDIO_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # ใช้คำนวณ "วันนี้" ของ dashboard ตามเวลาไทย
    APP_TIMEZONE: str = "Asia/Bangkok"
    # ค่าที่ใช้แสดงบน dashboard (มาจากผลประเมินโมเดล/สถิติ ไม่ได้คำนวณจาก DB)
    MODEL_ACCURACY: float = 96.4
    AVG_DAMAGE_PER_CASE_BAHT: int = 35000

    # จำนวนรายการสูงสุดต่อหน้าใน endpoint ที่ทำ pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # สร้างผู้ใช้/ข้อมูลตัวอย่างตอนรัน `python -m app.seed`
    SEED_DEMO_DATA: bool = True

    @field_validator("ENVIRONMENT")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return v.strip().lower()

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        # fail fast: ห้ามขึ้น production ด้วย secret ตัวอย่างหรือ secret ที่สั้นเกินไป
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET_KEY == INSECURE_SECRET or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY ต้องตั้งค่าแบบสุ่มยาว ≥ 32 ตัวอักษรใน production")
            if "*" in self.cors_origins:
                raise ValueError("ห้ามใช้ CORS_ORIGINS='*' ใน production")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
