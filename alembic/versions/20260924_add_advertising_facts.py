"""Add normalized advertising facts and preserve Yandex offer identity.

Revision ID: 20260924_advertising_facts
Revises: 20260923_product_economics
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_advertising_facts"
down_revision = "20260923_product_economics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_advertising_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("product_key", sa.String(length=160), nullable=False),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("seller_sku", sa.String(), nullable=True),
        sa.Column("marketplace_sku", sa.String(), nullable=True),
        sa.Column("is_unallocated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("orders", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("spend_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("attributed_revenue_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("allocation_method", sa.String(length=40), nullable=False),
        sa.Column("calculation_version", sa.String(length=30), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "business_date", "product_key", name="uq_fact_advertising_daily_product"),
    )
    for column in ("marketplace", "account_id", "business_date", "product_key", "master_product_id", "seller_sku", "marketplace_sku", "is_unallocated", "normalized_at"):
        op.create_index(f"ix_fact_advertising_daily_{column}", "fact_advertising_daily", [column])
    op.create_index("ix_fact_advertising_market_date", "fact_advertising_daily", ["marketplace", "business_date"])
    op.create_index("ix_fact_advertising_product_date", "fact_advertising_daily", ["master_product_id", "business_date"])

    op.add_column(
        "yandex_market_ad_daily_stats",
        sa.Column("offer_id", sa.String(), nullable=False, server_default=""),
    )
    op.create_index("ix_yandex_market_ad_daily_stats_offer_id", "yandex_market_ad_daily_stats", ["offer_id"])
    op.drop_constraint("uq_yandex_market_ad_daily_stat", "yandex_market_ad_daily_stats", type_="unique")
    op.create_unique_constraint(
        "uq_yandex_market_ad_daily_stat",
        "yandex_market_ad_daily_stats",
        ["business_id", "stat_date", "source", "campaign_id", "offer_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_yandex_market_ad_daily_stat", "yandex_market_ad_daily_stats", type_="unique")
    op.create_unique_constraint(
        "uq_yandex_market_ad_daily_stat",
        "yandex_market_ad_daily_stats",
        ["business_id", "stat_date", "source", "campaign_id"],
    )
    op.drop_index("ix_yandex_market_ad_daily_stats_offer_id", table_name="yandex_market_ad_daily_stats")
    op.drop_column("yandex_market_ad_daily_stats", "offer_id")
    op.drop_table("fact_advertising_daily")
