"""initial schema: ตาราง + PK + UNIQUE + FK (ยังไม่มี index เพื่อ performance)

Revision ID: 0001
Revises:
Create Date: 2026-10-02

Week 5-6: ความสัมพันธ์ของตาราง
  users 1──N reports, users 1──N call_logs, users 1──N emergency_contacts
  blacklist_numbers 1──N reports
  reports N──N scam_categories (ผ่าน report_categories)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NUMBER_STATUS = sa.Enum("safe", "suspect", "high_risk", name="numberstatus", native_enum=False, length=10)

CATEGORIES = [
    ("impersonate_police", "แอบอ้างเป็นตำรวจ/DSI"),
    ("impersonate_bank", "แอบอ้างเป็นเจ้าหน้าที่ธนาคาร"),
    ("parcel", "พัสดุผิดกฎหมาย/ค้างส่ง"),
    ("investment", "ชวนลงทุนผลตอบแทนสูง"),
    ("loan", "เงินกู้ออนไลน์"),
    ("refund", "คืนเงิน/ภาษี/ค่าไฟ"),
    ("voice_clone", "ใช้เสียงสังเคราะห์เลียนแบบคนรู้จัก"),
    ("other", "อื่น ๆ"),
]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=True),
        sa.Column("role", sa.Enum("gov", "bank", "telco", "admin", name="userrole",
                                  native_enum=False, length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("auto_notify", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_table(
        "blacklist_numbers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("status", NUMBER_STATUS, nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("report_count", sa.Integer(), nullable=False),
        sa.Column("first_reported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_reported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # 1 เบอร์ต้องมีได้แถวเดียว (กฎทางธุรกิจ) — เป็น unique index แบบ varchar_pattern_ops
    # เพื่อให้ index เดียวกันรองรับทั้ง = และ LIKE 'prefix%' (รายละเอียดใน 0002 / db-indexing)
    op.create_index("uq_blacklist_numbers_phone", "blacklist_numbers", ["phone_number"], unique=True,
                    postgresql_ops={"phone_number": "varchar_pattern_ops"})
    op.create_table(
        "scam_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "call_logs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("status", NUMBER_STATUS, nullable=False),
        sa.Column("is_synthetic_voice", sa.Boolean(), nullable=False),
        sa.Column("source", sa.Enum("number_check", "audio", "demo", name="callsource",
                                    native_enum=False, length=15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "emergency_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("blacklist_number_id", sa.Uuid(), nullable=False),
        sa.Column("reported_by", sa.Uuid(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blacklist_number_id"], ["blacklist_numbers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "report_categories",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["scam_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("report_id", "category_id"),
    )

    # ข้อมูลตั้งต้นของตาราง lookup
    categories = sa.table("scam_categories", sa.column("code", sa.String), sa.column("name", sa.String))
    op.bulk_insert(categories, [{"code": c, "name": n} for c, n in CATEGORIES])


def downgrade() -> None:
    op.drop_table("report_categories")
    op.drop_table("reports")
    op.drop_table("emergency_contacts")
    op.drop_table("call_logs")
    op.drop_table("scam_categories")
    op.drop_index("uq_blacklist_numbers_phone", table_name="blacklist_numbers")
    op.drop_table("blacklist_numbers")
    op.drop_table("token_blacklist")
    op.drop_table("users")
