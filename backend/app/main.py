"""
FastAPI entrypoint สำหรับ DetectCallcenter API
รวม router ทั้งหมด: auth, users, detect
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (import เพื่อให้ Base.metadata รู้จักทุก model)
from app.core.config import settings
from app.database import Base, engine
from app.routers import auth, detect, users

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

# CORS: เปิดกว้างไว้สำหรับ demo/dev — ก่อนขึ้น production ให้จำกัด allow_origins
# เป็นโดเมนจริงของ frontend เท่านั้น
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    # สร้างตารางอัตโนมัติถ้ายังไม่มี — สะดวกสำหรับ dev/demo
    # สำหรับ production แนะนำใช้ Alembic migration แทน (ดู README)
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(detect.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
