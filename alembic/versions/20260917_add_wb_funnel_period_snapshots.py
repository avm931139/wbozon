"""Add arbitrary-period WB Sales Funnel product snapshots.

Revision ID: 20260917_wb_funnel_periods
Revises: 20260917_yandex_business_scope
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_wb_funnel_periods"
down_revision = "20260917_yandex_business_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_sales_funnel_period_products",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("vendor_code", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cart_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("buyout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyout_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("cancel_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "period_from", "period_to", "nm_id",
            name="uq_wb_sales_funnel_period_product",
        ),
    )
    for column in ("period_from", "period_to", "nm_id", "vendor_code", "fetched_at"):
        op.create_index(
            f"ix_wb_sales_funnel_period_products_{column}",
            "wb_sales_funnel_period_products",
            [column],
        )


def downgrade() -> None:
    op.drop_table("wb_sales_funnel_period_products")
