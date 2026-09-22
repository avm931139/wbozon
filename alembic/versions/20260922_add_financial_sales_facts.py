"""Add normalized financial sales facts and product barcodes.

Revision ID: 20260922_financial_sales_facts
Revises: 20260917_wb_warehouse_remains
"""

from alembic import op
import sqlalchemy as sa


revision = "20260922_financial_sales_facts"
down_revision = "20260917_wb_warehouse_remains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_fact_sync_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("facts_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lineage_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("barcode_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_products", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_analytics_fact_sync_runs_marketplace", "analytics_fact_sync_runs", ["marketplace"])
    op.create_index("ix_analytics_fact_sync_runs_started_at", "analytics_fact_sync_runs", ["started_at"])
    op.create_index("ix_analytics_fact_sync_runs_status", "analytics_fact_sync_runs", ["status"])

    op.create_table(
        "product_barcodes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("marketplace_product_link_id", sa.Integer(), sa.ForeignKey("marketplace_product_links.id", ondelete="CASCADE"), nullable=False),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("external_product_id", sa.String(), nullable=False),
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("barcode_type", sa.String(length=30), nullable=False, server_default="marketplace"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_table", sa.String(length=100), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "barcode", name="uq_product_barcode_marketplace_account"),
    )
    for column in (
        "master_product_id", "marketplace_product_link_id", "marketplace",
        "account_id", "external_product_id", "barcode", "active",
    ):
        op.create_index(f"ix_product_barcodes_{column}", "product_barcodes", [column])

    op.create_table(
        "fact_sales",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("store_id", sa.String(), nullable=True),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("marketplace_product_link_id", sa.Integer(), sa.ForeignKey("marketplace_product_links.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seller_sku", sa.String(), nullable=True),
        sa.Column("marketplace_sku", sa.String(), nullable=True),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("posting_id", sa.String(), nullable=True),
        sa.Column("operation_id", sa.String(), nullable=True),
        sa.Column("fulfillment_type", sa.String(length=20), nullable=True),
        sa.Column("warehouse_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("unit_price_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("gross_amount_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("discount_amount_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("marketplace_discount_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("customer_paid_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("sales_amount_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("return_amount_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("compensation_amount_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("net_revenue_exact", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("unit_cost_exact", sa.Numeric(20, 6), nullable=True),
        sa.Column("cost_amount_exact", sa.Numeric(20, 6), nullable=True),
        sa.Column("unit_price_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("gross_amount_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("discount_amount_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("marketplace_discount_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("customer_paid_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sales_amount_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("return_amount_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("compensation_amount_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("net_revenue_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("unit_cost_kopecks", sa.BigInteger(), nullable=True),
        sa.Column("cost_amount_kopecks", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="RUB"),
        sa.Column("cost_record_id", sa.Integer(), sa.ForeignKey("product_cost_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cost_status", sa.String(length=20), nullable=False, server_default="missing"),
        sa.Column("source_event_key", sa.String(length=128), nullable=False),
        sa.Column("source_table", sa.String(length=100), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("source_operation_key", sa.String(), nullable=False),
        sa.Column("source_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("calculation_version", sa.String(length=30), nullable=False),
        sa.Column("is_financial", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_preliminary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "source_event_key", name="uq_fact_sales_source_event"),
    )
    indexed = (
        "marketplace", "account_id", "store_id", "master_product_id",
        "marketplace_product_link_id", "seller_sku", "marketplace_sku",
        "offer_id", "order_id", "posting_id", "operation_id",
        "fulfillment_type", "warehouse_id", "event_type", "event_at",
        "business_date", "currency", "cost_record_id", "cost_status",
        "source_payload_hash", "is_financial", "is_preliminary", "normalized_at",
    )
    for column in indexed:
        op.create_index(f"ix_fact_sales_{column}", "fact_sales", [column])
    op.create_index("ix_fact_sales_marketplace_business_date", "fact_sales", ["marketplace", "business_date"])
    op.create_index("ix_fact_sales_product_business_date", "fact_sales", ["master_product_id", "business_date"])
    op.create_index("ix_fact_sales_account_business_date", "fact_sales", ["account_id", "business_date"])

    op.create_table(
        "fact_sale_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fact_sale_id", sa.BigInteger(), sa.ForeignKey("fact_sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_table", sa.String(length=100), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("source_operation_key", sa.String(), nullable=True),
        sa.Column("source_payload_hash", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("fact_sale_id", "source_table", "source_record_id", name="uq_fact_sale_source_row"),
    )
    op.create_index("ix_fact_sale_sources_fact_sale_id", "fact_sale_sources", ["fact_sale_id"])
    op.create_index("ix_fact_sale_sources_source_table", "fact_sale_sources", ["source_table"])


def downgrade() -> None:
    op.drop_table("fact_sale_sources")
    op.drop_table("fact_sales")
    op.drop_table("product_barcodes")
    op.drop_table("analytics_fact_sync_runs")
