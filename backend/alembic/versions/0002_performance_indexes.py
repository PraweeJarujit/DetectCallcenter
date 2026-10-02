"""performance indexes (IDX-2 ถึง IDX-9) — ออกแบบจาก query จริงของ API

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02

แยกเป็น migration ของตัวเองเพื่อให้:
  1) เห็นชัดว่า index ไหนเพิ่มมาเพื่ออะไร (ดูตารางเต็มใน db-indexing/README.md)
  2) สร้างบนฐานข้อมูลที่มีข้อมูลอยู่แล้วได้ด้วย CREATE INDEX CONCURRENTLY
     (ไม่ lock ตาราง — ระบบยังรับ INSERT/UPDATE ได้ระหว่างสร้าง index)
  3) downgrade (DROP) เพื่อทดลองเทียบความเร็วก่อน/หลังได้ทันที
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HIGH_RISK = sa.text("risk_score >= 80")
USER_NOT_NULL = sa.text("user_id IS NOT NULL")

# (ชื่อ, ตาราง, columns, kwargs เพิ่มเติม)
INDEXES = [
    # blacklist_numbers — หน้า Blacklist เรียงตาม risk_score (มี/ไม่มี filter status)
    ("ix_blacklist_numbers_status_risk", "blacklist_numbers", ["status", sa.text("risk_score DESC"), "id"], {}),
    ("ix_blacklist_numbers_risk", "blacklist_numbers", [sa.text("risk_score DESC"), "id"], {}),
    # reports — FK ไม่มี index อัตโนมัติใน Postgres
    ("ix_reports_blacklist_created", "reports", ["blacklist_number_id", sa.text("created_at DESC")], {}),
    ("ix_reports_reporter_created", "reports", ["reported_by", sa.text("created_at DESC")], {}),
    # report_categories — ค้นกลับจาก category -> reports
    ("ix_report_categories_category", "report_categories", ["category_id"], {}),
    # call_logs — dashboard
    ("ix_call_logs_created", "call_logs", [sa.text("created_at DESC"), sa.text("id DESC")], {}),
    ("ix_call_logs_high_risk_created", "call_logs", ["created_at"],
     {"postgresql_where": HIGH_RISK, "sqlite_where": HIGH_RISK}),
    ("ix_call_logs_user_created", "call_logs", ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
     {"postgresql_where": USER_NOT_NULL, "sqlite_where": USER_NOT_NULL}),
    # emergency_contacts
    ("ix_emergency_contacts_user", "emergency_contacts", ["user_id"], {}),
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        # CONCURRENTLY ทำใน transaction ไม่ได้ -> ใช้ autocommit block
        with op.get_context().autocommit_block():
            for name, table, cols, kw in INDEXES:
                op.create_index(name, table, cols, postgresql_concurrently=True, if_not_exists=True, **kw)
            for table in ("blacklist_numbers", "reports", "call_logs"):
                op.execute(f"ANALYZE {table}")  # อัปเดตสถิติให้ planner เลือกใช้ index ใหม่ทันที
    else:
        for name, table, cols, kw in INDEXES:
            op.create_index(name, table, cols, **kw)


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            for name, table, _cols, _kw in reversed(INDEXES):
                op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
    else:
        for name, table, _cols, _kw in reversed(INDEXES):
            op.drop_index(name, table_name=table)
