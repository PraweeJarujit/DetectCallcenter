FROM python:3.12-slim

# ป้องกันการสร้าง .pyc และให้ log ออกทันที (ไม่ buffer)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl ใช้กับ HEALTHCHECK (psycopg2-binary มี libpq มาในตัวแล้ว ไม่ต้องติดตั้ง gcc)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh .

# Security: ไม่รันแอปด้วย root
# ตัด CRLF (กรณี checkout บน Windows) ไม่งั้น sh รันสคริปต์ไม่ได้
RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && useradd --create-home --uid 10001 appuser && chmod +x docker-entrypoint.sh && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/api/health || exit 1

# entrypoint: alembic upgrade head -> seed (ถ้าเปิด) -> uvicorn
CMD ["./docker-entrypoint.sh"]
