"""
FastAPI entrypoint สำหรับ DetectCallcenter API
รวม router ทั้งหมด: auth, users, detect, calls, contacts

ลำดับ middleware (นอก -> ใน): CORS -> RequestContext (request id + access log) -> SecurityHeaders
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import models  # noqa: F401  (import เพื่อให้ Base.metadata รู้จักทุก model)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestContextMiddleware, SecurityHeadersMiddleware, setup_logging
from app.database import SessionLocal
from app.routers import auth, billing, calls, contacts, detect, live, users

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("app")

# ตารางถูกสร้าง/อัปเดตด้วย Alembic migration (`alembic upgrade head`) ไม่ใช้ create_all ตอน startup แล้ว
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    description="AwayCall — API ตรวจจับแก๊งคอลเซ็นเตอร์ (FastAPI + PostgreSQL)",
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
# CORS: อนุญาตเฉพาะ origin ที่ตั้งไว้ใน CORS_ORIGINS (ห้าม "*" ใน production — ตรวจใน config.py)
# ใช้ Bearer token ใน header ไม่ใช้ cookie จึงไม่ต้องเปิด allow_credentials (ลดความเสี่ยง CSRF)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Response-Time-ms"],
)

register_exception_handlers(app)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(detect.router, prefix="/api")
app.include_router(calls.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(live.router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health_check():
    """ใช้กับ Docker HEALTHCHECK / load balancer — ตรวจว่าต่อฐานข้อมูลได้จริง"""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:  # pragma: no cover - ทดสอบด้วยการปิด DB จริง
        logger.exception("health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
