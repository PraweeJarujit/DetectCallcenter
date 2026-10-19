"""subscription 59 บาท/เดือน + ฟอร์มติดต่อเรา + ตรวจข้อความ

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19

- เปลี่ยนจากขายให้องค์กร (role gov/bank/telco) เป็นสมาชิกบุคคล: role เหลือ member / admin
- users: premium_until, auto_renew (สิทธิ์ Premium ดูจากวันหมดอายุ)
- payments: ประวัติการชำระค่าสมาชิก (users 1──N payments)
- contact_messages: ข้อความจากหน้า "ติดต่อเรา"
- call_logs.phone_number เป็น NULL ได้ (ตรวจข้อความ/ไฟล์เสียงโดยไม่ระบุเบอร์)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'member' WHERE role IN ('gov', 'bank', 'telco')")
    op.add_column("users", sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("auto_renew", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.alter_column("call_logs", "phone_number", existing_type=sa.String(20), nullable=True)

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount_baht", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "paid", "expired", "cancelled", name="paymentstatus",
                                    native_enum=False, length=10), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_ref", sa.String(64), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_ref"),
    )
    op.create_index("ix_payments_user_created", "payments", ["user_id", sa.text("created_at DESC")])

    op.create_table(
        "contact_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("topic", sa.String(30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("new", "handled", name="contactstatus", native_enum=False, length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_messages_status_created", "contact_messages", ["status", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_contact_messages_status_created", table_name="contact_messages")
    op.drop_table("contact_messages")
    op.drop_index("ix_payments_user_created", table_name="payments")
    op.drop_table("payments")
    op.execute("DELETE FROM call_logs WHERE phone_number IS NULL")
    op.alter_column("call_logs", "phone_number", existing_type=sa.String(20), nullable=False)
    op.drop_column("users", "auto_renew")
    op.drop_column("users", "premium_until")
    op.execute("UPDATE users SET role = 'gov' WHERE role = 'member'")
