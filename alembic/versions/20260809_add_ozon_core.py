"""add Ozon products, stocks, and postings

Revision ID: 20260809_ozon_core
Revises: 20260809_telegram_reports
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_ozon_core"
down_revision = "20260809_telegram_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ozon_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("sku", sa.BigInteger(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("old_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id"),
        comment="Товары кабинета Ozon Seller.",
    )
    for column in ("id", "product_id", "offer_id", "sku", "barcode", "status", "visibility"):
        op.create_index(f"ix_ozon_products_{column}", "ozon_products", [column])

    op.create_table(
        "ozon_stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("stock_type", sa.String(), nullable=False),
        sa.Column("present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "stock_type", name="uq_ozon_stock_product_type"),
        comment="Текущие остатки товаров Ozon по схеме хранения.",
    )
    for column in ("id", "product_id", "offer_id", "stock_type"):
        op.create_index(f"ix_ozon_stocks_{column}", "ozon_stocks", [column])

    op.create_table(
        "ozon_postings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("posting_number", sa.String(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("order_number", sa.String(), nullable=True),
        sa.Column("scheme", sa.String(10), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("substatus", sa.String(), nullable=True),
        sa.Column("in_process_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipment_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("products", sa.JSON(), nullable=False),
        sa.Column("analytics_data", sa.JSON(), nullable=True),
        sa.Column("financial_data", sa.JSON(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("posting_number", "scheme", name="uq_ozon_posting_number_scheme"),
        comment="Отправления Ozon FBS и FBO.",
    )
    for column in ("id", "posting_number", "order_id", "order_number", "scheme", "status", "substatus", "in_process_at", "shipment_date"):
        op.create_index(f"ix_ozon_postings_{column}", "ozon_postings", [column])


def downgrade() -> None:
    op.drop_table("ozon_postings")
    op.drop_table("ozon_stocks")
    op.drop_table("ozon_products")
