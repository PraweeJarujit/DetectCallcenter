#!/bin/sh
# ลำดับการเริ่มระบบ: migrate schema -> ใส่ข้อมูลตั้งต้น -> start API
set -e

echo ">>> alembic upgrade head"
alembic upgrade head

echo ">>> seed (categories + demo data ถ้า SEED_DEMO_DATA=true)"
python -m app.seed

echo ">>> starting uvicorn on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
     --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --no-server-header
