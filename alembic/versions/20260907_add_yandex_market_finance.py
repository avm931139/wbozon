"""Add Yandex Market finance transaction ledger."""

from alembic import op
import sqlalchemy as sa


revision = "20260907_yandex_finance"
down_revision = "20260907_ozon_accrual_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "yandex_market_finance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("partner_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("transaction_source", sa.String(), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("product_or_service", sa.String(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_hash", name="uq_yandex_market_finance_source_hash"),
    )
    for name in ("source_hash", "business_id", "partner_id", "transaction_at", "transaction_id", "transaction_type", "transaction_source", "order_id", "offer_id", "fetched_at"):
        op.create_index(f"ix_yandex_market_finance_transactions_{name}", "yandex_market_finance_transactions", [name])


def downgrade() -> None:
    op.drop_table("yandex_market_finance_transactions")
