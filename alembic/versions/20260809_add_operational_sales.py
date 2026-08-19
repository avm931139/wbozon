"""add normalized operational WB orders, sales and returns

Revision ID: 20260809_operational_sales
Revises: 20260809_wb_sync_logging
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_operational_sales"
down_revision = "20260809_wb_sync_logging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    money = sa.Numeric(20, 6)
    op.create_table(
        "wb_operational_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("srid", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id"), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_change_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_cancel", sa.Boolean(), nullable=False),
        sa.Column("warehouse_name", sa.String(), nullable=True),
        sa.Column("warehouse_type", sa.String(), nullable=True),
        sa.Column("supplier_article", sa.String(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("finished_price", money, nullable=False),
        sa.Column("price_with_discount", money, nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_wb_operational_orders_srid", "wb_operational_orders", ["srid"], unique=True)
    for column in ("product_id", "nm_id", "order_date", "last_change_date", "cancel_date", "is_cancel", "warehouse_type", "supplier_article", "barcode"):
        op.create_index(f"ix_wb_operational_orders_{column}", "wb_operational_orders", [column])

    op.create_table(
        "wb_operational_sales",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("sale_id", sa.String(), nullable=False),
        sa.Column("srid", sa.String(), nullable=False),
        sa.Column("operation_type", sa.String(20), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id"), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_change_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warehouse_name", sa.String(), nullable=True),
        sa.Column("warehouse_type", sa.String(), nullable=True),
        sa.Column("supplier_article", sa.String(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("finished_price", money, nullable=False),
        sa.Column("price_with_discount", money, nullable=False),
        sa.Column("for_pay", money, nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_wb_operational_sales_sale_id", "wb_operational_sales", ["sale_id"], unique=True)
    for column in ("srid", "operation_type", "product_id", "nm_id", "event_date", "last_change_date", "warehouse_type", "supplier_article", "barcode"):
        op.create_index(f"ix_wb_operational_sales_{column}", "wb_operational_sales", [column])


def downgrade() -> None:
    op.drop_table("wb_operational_sales")
    op.drop_table("wb_operational_orders")
