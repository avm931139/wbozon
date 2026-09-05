"""add Yandex Market identity, catalog and orders

Revision ID: 20260905_yandex_market_core
Revises: 20260904_wb_order_feed
"""

from alembic import op
import sqlalchemy as sa


revision = "20260905_yandex_market_core"
down_revision = "20260904_wb_order_feed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yandex_market_stocks", sa.Column("turnover", sa.String(length=20), nullable=True))
    op.add_column("yandex_market_stocks", sa.Column("turnover_days", sa.Float(), nullable=True))
    op.create_index("ix_yandex_market_stocks_turnover", "yandex_market_stocks", ["turnover"])
    op.add_column("yandex_market_stock_snapshots", sa.Column("turnover", sa.String(length=20), nullable=True))
    op.add_column("yandex_market_stock_snapshots", sa.Column("turnover_days", sa.Float(), nullable=True))
    op.create_index(
        "ix_yandex_market_stock_snapshots_turnover",
        "yandex_market_stock_snapshots",
        ["turnover"],
    )
    op.create_table(
        "yandex_market_businesses",
        sa.Column("business_id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_yandex_market_businesses_fetched_at", "yandex_market_businesses", ["fetched_at"])

    op.create_table(
        "yandex_market_campaigns",
        sa.Column("campaign_id", sa.BigInteger(), primary_key=True),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("placement_type", sa.String(length=20), nullable=True),
        sa.Column("api_availability", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("business_id", "placement_type", "api_availability", "fetched_at"):
        op.create_index(f"ix_yandex_market_campaigns_{column}", "yandex_market_campaigns", [column])

    op.create_table(
        "yandex_market_warehouses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=True),
        sa.Column("warehouse_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("models", sa.JSON(), nullable=False),
        sa.Column("address", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "business_id", "warehouse_id", "warehouse_type", name="uq_yandex_market_warehouse"
        ),
    )
    for column in ("business_id", "warehouse_id", "campaign_id", "warehouse_type", "fetched_at"):
        op.create_index(f"ix_yandex_market_warehouses_{column}", "yandex_market_warehouses", [column])

    op.create_table(
        "yandex_market_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("market_sku", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("vendor", sa.String(), nullable=True),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("barcodes", sa.JSON(), nullable=False),
        sa.Column("pictures", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "offer_id", name="uq_yandex_market_offer"),
    )
    for column in ("business_id", "offer_id", "market_sku", "category_name", "status", "fetched_at"):
        op.create_index(f"ix_yandex_market_offers_{column}", "yandex_market_offers", [column])

    op.create_table(
        "yandex_market_campaign_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("availability", sa.Boolean(), nullable=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("old_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("campaign_id", "offer_id", name="uq_yandex_market_campaign_offer"),
    )
    for column in ("campaign_id", "offer_id", "status", "availability", "fetched_at"):
        op.create_index(f"ix_yandex_market_campaign_offers_{column}", "yandex_market_campaign_offers", [column])

    op.create_table(
        "yandex_market_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("external_order_id", sa.String(), nullable=True),
        sa.Column("campaign_id", sa.BigInteger(), nullable=True),
        sa.Column("program_type", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("substatus", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipment_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_type", sa.String(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "order_id", name="uq_yandex_market_order"),
    )
    for column in (
        "business_id", "order_id", "external_order_id", "campaign_id", "program_type",
        "status", "substatus", "created_at", "updated_at", "shipment_date",
        "delivery_date", "fetched_at",
    ):
        op.create_index(f"ix_yandex_market_orders_{column}", "yandex_market_orders", [column])

    op.create_table(
        "yandex_market_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("market_sku", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("subsidy", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("statuses", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "order_id", "item_key", name="uq_yandex_market_order_item"),
    )
    for column in ("business_id", "order_id", "offer_id", "market_sku", "fetched_at"):
        op.create_index(f"ix_yandex_market_order_items_{column}", "yandex_market_order_items", [column])

    op.create_table(
        "yandex_market_sync_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    for column in ("task", "started_at", "status"):
        op.create_index(f"ix_yandex_market_sync_runs_{column}", "yandex_market_sync_runs", [column])


def downgrade() -> None:
    op.drop_table("yandex_market_sync_runs")
    op.drop_table("yandex_market_order_items")
    op.drop_table("yandex_market_orders")
    op.drop_table("yandex_market_campaign_offers")
    op.drop_table("yandex_market_offers")
    op.drop_table("yandex_market_warehouses")
    op.drop_table("yandex_market_campaigns")
    op.drop_table("yandex_market_businesses")
    op.drop_index("ix_yandex_market_stock_snapshots_turnover", table_name="yandex_market_stock_snapshots")
    op.drop_column("yandex_market_stock_snapshots", "turnover_days")
    op.drop_column("yandex_market_stock_snapshots", "turnover")
    op.drop_index("ix_yandex_market_stocks_turnover", table_name="yandex_market_stocks")
    op.drop_column("yandex_market_stocks", "turnover_days")
    op.drop_column("yandex_market_stocks", "turnover")
