"""add Yandex Market advertising daily statistics

Revision ID: 20260906_yandex_market_ads
Revises: 20260905_yandex_market_core
"""

from alembic import op
import sqlalchemy as sa


revision = "20260906_yandex_market_ads"
down_revision = "20260905_yandex_market_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "yandex_market_ad_daily_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("campaign_name", sa.String(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spend", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("attributed_revenue", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "stat_date", "source", "campaign_id", name="uq_yandex_market_ad_daily_stat"
        ),
    )
    for column in ("stat_date", "source", "business_id", "campaign_id", "fetched_at"):
        op.create_index(
            f"ix_yandex_market_ad_daily_stats_{column}",
            "yandex_market_ad_daily_stats",
            [column],
        )


def downgrade() -> None:
    op.drop_table("yandex_market_ad_daily_stats")
