"""add separate FBS and FBO order history

Revision ID: 20260809_add_fbs_fbo_orders
Revises: 20260809_split_fbs_fbo
Create Date: 2026-08-09 00:00:03.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_add_fbs_fbo_orders"
down_revision = "20260809_split_fbs_fbo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_fbs_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("order_uid", sa.String()), sa.Column("rid", sa.String()),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id")),
        sa.Column("size_id", sa.Integer(), sa.ForeignKey("wb_product_sizes.id")),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("wb_fbs_warehouses.id")),
        sa.Column("warehouse_wb_id", sa.BigInteger()), sa.Column("office_id", sa.BigInteger()),
        sa.Column("created_at_wb", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supply_id", sa.String()), sa.Column("delivery_type", sa.String()),
        sa.Column("article", sa.String()), sa.Column("color_code", sa.String()),
        sa.Column("skus", sa.JSON()), sa.Column("price", sa.BigInteger()),
        sa.Column("scan_price", sa.BigInteger()), sa.Column("converted_price", sa.BigInteger()),
        sa.Column("currency_code", sa.Integer()), sa.Column("converted_currency_code", sa.Integer()),
        sa.Column("cargo_type", sa.Integer()), sa.Column("cross_border_type", sa.Integer()),
        sa.Column("is_zero_order", sa.Boolean(), nullable=False), sa.Column("is_b2b", sa.Boolean(), nullable=False),
        sa.Column("supplier_status", sa.String()), sa.Column("wb_status", sa.String()),
        sa.Column("address", sa.JSON()), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for column in ("id", "order_id", "order_uid", "rid", "product_id", "size_id", "warehouse_id", "warehouse_wb_id", "created_at_wb", "supply_id", "supplier_status", "wb_status"):
        op.create_index(f"ix_wb_fbs_orders_{column}", "wb_fbs_orders", [column], unique=column == "order_id")

    op.create_table(
        "wb_fbo_orders",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("srid", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id")),
        sa.Column("size_id", sa.Integer(), sa.ForeignKey("wb_product_sizes.id")),
        sa.Column("order_date", sa.DateTime(), nullable=False), sa.Column("last_change_date", sa.DateTime(), nullable=False),
        sa.Column("warehouse_name", sa.String()), sa.Column("warehouse_type", sa.String()),
        sa.Column("country_name", sa.String()), sa.Column("federal_district_name", sa.String()), sa.Column("region_name", sa.String()),
        sa.Column("supplier_article", sa.String()), sa.Column("barcode", sa.String()),
        sa.Column("category", sa.String()), sa.Column("subject", sa.String()), sa.Column("brand", sa.String()), sa.Column("tech_size", sa.String()),
        sa.Column("income_id", sa.BigInteger()), sa.Column("is_supply", sa.Boolean(), nullable=False), sa.Column("is_realization", sa.Boolean(), nullable=False),
        sa.Column("total_price", sa.Float()), sa.Column("discount_percent", sa.Float()), sa.Column("spp", sa.Float()),
        sa.Column("finished_price", sa.Float()), sa.Column("price_with_discount", sa.Float()),
        sa.Column("is_cancel", sa.Boolean(), nullable=False), sa.Column("cancel_date", sa.DateTime()),
        sa.Column("sticker", sa.String()), sa.Column("g_number", sa.String()), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for column in ("id", "srid", "product_id", "size_id", "order_date", "last_change_date", "warehouse_name", "warehouse_type", "supplier_article", "barcode", "is_cancel", "g_number"):
        op.create_index(f"ix_wb_fbo_orders_{column}", "wb_fbo_orders", [column], unique=column == "srid")


def downgrade() -> None:
    op.drop_table("wb_fbo_orders")
    op.drop_table("wb_fbs_orders")
