"""add Telegram report delivery ledger

Revision ID: 20260809_telegram_reports
Revises: 20260809_operational_sales
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_telegram_reports"
down_revision = "20260809_operational_sales"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_telegram_deliveries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("report_key", sa.String(100), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("chat_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message_hash", sa.String(64), nullable=True),
        sa.Column("telegram_message_ids", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_wb_telegram_deliveries_report_key", "wb_telegram_deliveries", ["report_key"], unique=True)
    for column in ("report_type", "status", "created_at"):
        op.create_index(f"ix_wb_telegram_deliveries_{column}", "wb_telegram_deliveries", [column])


def downgrade() -> None:
    op.drop_table("wb_telegram_deliveries")
