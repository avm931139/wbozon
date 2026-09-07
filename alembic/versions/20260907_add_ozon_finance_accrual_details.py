"""add Ozon finance accrual types and posting details

Revision ID: 20260907_ozon_accruals
Revises: 20260907_fin_reconcile
"""

from alembic import op
import sqlalchemy as sa


revision = "20260907_ozon_accruals"
down_revision = "20260907_fin_reconcile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ozon_finance_accrual_types",
        sa.Column("type_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ozon_finance_posting_accruals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("posting_number", sa.String(), nullable=False),
        sa.Column("accrual_date", sa.Date(), nullable=True),
        sa.Column("type_id", sa.Integer(), sa.ForeignKey("ozon_finance_accrual_types.type_id"), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("seller_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("accrued", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_hash", name="uq_ozon_finance_posting_accrual_hash"),
    )
    for column in ("source_hash", "posting_number", "accrual_date", "type_id", "sku", "fetched_at"):
        op.create_index(f"ix_ozon_finance_posting_accruals_{column}", "ozon_finance_posting_accruals", [column])
    op.execute("""
        UPDATE ozon_finance_accruals
        SET posting_number = raw_data ->> 'unit_number'
        WHERE (posting_number IS NULL OR posting_number = '')
          AND coalesce(raw_data ->> 'unit_number', '') <> ''
          AND coalesce(raw_data ->> 'accrued_category', '') = 'POSTING'
          AND (raw_data ->> 'unit_number') ~ '^[0-9]{1,32}-[0-9]{1,32}-[0-9]{1,32}$'
    """)


def downgrade() -> None:
    op.drop_table("ozon_finance_posting_accruals")
    op.drop_table("ozon_finance_accrual_types")
