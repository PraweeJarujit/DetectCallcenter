"""
Logging & middleware (Week 3-4: Logging & debugging techniques / Week 11-12: Security headers)

- setup_logging(): ตั้ง format log กลาง ใส่ request_id ทุกบรรทัด
- RequestContextMiddleware: สร้าง request_id ต่อ request, จับเวลา, log method/path/status/ms
  และส่ง X-Request-ID กลับใน response (ใช้ไล่ log คู่กับ DevTools > Network tab)
- SecurityHeadersMiddleware: header กัน XSS / clickjacking / MIME sniffing
"""
import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
access_logger = logging.getLogger("app.access")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s"
    ))
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger("app")
    root.handlers = [handler]
    root.setLevel(level.upper())
    root.propagate = False


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # รับ X-Request-ID จาก proxy ถ้ามี (ตัดความยาวกัน header injection) ไม่งั้นสร้างใหม่
        incoming = request.headers.get("x-request-id", "")
        rid = incoming[:64] if incoming.replace("-", "").isalnum() else uuid.uuid4().hex[:16]
        request.state.request_id = rid
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = rid
            response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
            log = access_logger.warning if elapsed_ms > 500 else access_logger.info  # request ช้าเกิน 500ms เด่นใน log
            log("%s %s -> %s (%.1f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
            return response
        finally:
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    # /docs และ /redoc โหลด Swagger UI จาก CDN จึงไม่ใส่ CSP เข้มให้ path เหล่านี้
    _DOC_PATHS = ("/docs", "/redoc", "/openapi.json")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.url.path.startswith(self._DOC_PATHS):
            # API คืน JSON เท่านั้น — ห้ามโหลด/รันอะไรทั้งสิ้นถ้าเผลอถูกเปิดเป็น HTML
            h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if request.url.scheme == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
