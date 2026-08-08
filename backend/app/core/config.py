"""
ตั้งค่าแอปทั้งหมดแบบรวมศูนย์ อ่านค่าจาก environment variables / .env
ใช้ pydantic-settings เพื่อ validate ค่าตั้งแต่ตอน startup (fail fast ถ้าลืมตั้งค่า secret)
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "DetectCallcenter API"

    DATABASE_URL: str = "postgresql+psycopg2://dcc_user:dcc_password@db:5432/detectcallcenter"

    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    VOICEGUARD_AI_URL: str = "http://voiceguard-ai:9000"

    # จำนวนรายการสูงสุดต่อหน้าใน endpoint ที่ทำ pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100


settings = Settings()
