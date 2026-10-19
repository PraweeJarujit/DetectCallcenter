"""
Custom exceptions + global exception handlers (Week 3-4: Error handling & HTTP status codes)

ทุก error ที่ออกจาก API จะมีรูปแบบเดียวกันเสมอ ให้ frontend อ่านง่าย:

    {
      "success": false,
      "error": {"code": "NOT_FOUND", "message": "ไม่พบผู้ใช้งาน", "details": [...]},
      "request_id": "a1b2c3..."
    }
"""
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """ฐานของ error ทางธุรกิจทั้งหมด — subclass กำหนด status_code และ code ไว้ให้"""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, details: Any | None = None, headers: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "ไม่สามารถยืนยันตัวตนได้ (invalid or expired token)", **kw):
        kw.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kw)


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "PAYLOAD_TOO_LARGE"


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "TOO_MANY_REQUESTS"


class PremiumRequiredError(AppError):
    """ฟีเจอร์นี้สำหรับสมาชิก Premium (59 บาท/เดือน) — 402 Payment Required"""
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "PREMIUM_REQUIRED"


class QuotaExceededError(AppError):
    """ใช้สิทธิ์ฟรีครบโควตาของวันนี้แล้ว"""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "QUOTA_EXCEEDED"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "AI_UNAVAILABLE"


_HTTP_CODE_NAMES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(request: Request, status_code: int, code: str, message: str,
                   details: Any | None = None, headers: dict | None = None) -> JSONResponse:
    body: dict[str, Any] = {"success": False, "error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    body["request_id"] = _request_id(request)
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def _format_validation_errors(exc: RequestValidationError) -> list[dict]:
    out = []
    for err in exc.errors():
        # loc เช่น ("body", "phone_number") -> "phone_number"
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        msg = err.get("msg", "")
        # pydantic ใส่ prefix "Value error, " ให้ ValueError จาก custom validator — ตัดออกให้อ่านง่าย
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        out.append({"field": ".".join(loc) or None, "message": msg, "type": err.get("type")})
    return out


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        logger.info("AppError %s %s: %s", exc.status_code, exc.code, exc.message)
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        details = _format_validation_errors(exc)
        first = details[0]["message"] if details else ""
        return error_response(
            request, 422, "VALIDATION_ERROR", f"ข้อมูลที่ส่งมาไม่ถูกต้อง: {first}", details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODE_NAMES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else code
        return error_response(request, exc.status_code, code, message,
                              headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # log stack trace เต็มฝั่ง server แต่ไม่ส่งรายละเอียดภายในกลับไปให้ client (ป้องกันข้อมูลรั่ว)
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(request, 500, "INTERNAL_ERROR", "เกิดข้อผิดพลาดภายในระบบ กรุณาลองใหม่อีกครั้ง")
