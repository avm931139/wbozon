"""Add daily product economics analytical facts.

Revision ID: 20260923_product_economics
Revises: 20260922_financial_sales_facts
"""

from alembic import op
import sqlalchemy as sa


revision = "20260923_product_economics"
down_revision = "20260922_financial_sales_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_product_economics_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("product_key", sa.String(length=160), nullable=False),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("seller_sku", sa.String(), nullable=True),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("is_unallocated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_revenue_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("compensation_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("revenue_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("marketplace_expense_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("logistics_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("advertising_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("profit_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("missing_cost_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expense_allocation_method", sa.String(length=40), nullable=False),
        sa.Column("advertising_allocation_method", sa.String(length=40), nullable=False),
        sa.Column("calculation_version", sa.String(length=30), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "business_date", "product_key", name="uq_fact_product_economics_daily_key"),
    )
    for column in ("marketplace", "account_id", "business_date", "product_key", "master_product_id", "seller_sku", "is_unallocated", "normalized_at"):
        op.create_index(f"ix_fact_product_economics_daily_{column}", "fact_product_economics_daily", [column])
    op.create_index("ix_fact_product_economics_market_date", "fact_product_economics_daily", ["marketplace", "business_date"])
    op.create_index("ix_fact_product_economics_product_date", "fact_product_economics_daily", ["master_product_id", "business_date"])

    op.create_table(
        "fact_product_economics_controls",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("revenue_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("marketplace_expense_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("logistics_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("advertising_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("advertising_unallocated_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("profit_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("product_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_complete", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("calculation_version", sa.String(length=30), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "business_date", name="uq_fact_product_economics_control_day"),
    )
    for column in ("marketplace", "account_id", "business_date", "normalized_at"):
        op.create_index(f"ix_fact_product_economics_controls_{column}", "fact_product_economics_controls", [column])
    op.create_index("ix_fact_product_economics_control_market_date", "fact_product_economics_controls", ["marketplace", "business_date"])


def downgrade() -> None:
    op.drop_table("fact_product_economics_controls")
    op.drop_table("fact_product_economics_daily")
