"""Scope Yandex Market finance and advertising uniqueness by business.

Revision ID: 20260917_yandex_business_scope
Revises: 20260911_wb_funnel_account
"""

from alembic import op


revision = "20260917_yandex_business_scope"
down_revision = "20260911_wb_funnel_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_yandex_market_ad_daily_stat",
        "yandex_market_ad_daily_stats",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_yandex_market_ad_daily_stat",
        "yandex_market_ad_daily_stats",
        ["business_id", "stat_date", "source", "campaign_id"],
    )
    op.drop_constraint(
        "uq_yandex_market_finance_source_hash",
        "yandex_market_finance_transactions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_yandex_market_finance_source_hash",
        "yandex_market_finance_transactions",
        ["business_id", "source_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_yandex_market_finance_source_hash",
        "yandex_market_finance_transactions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_yandex_market_finance_source_hash",
        "yandex_market_finance_transactions",
        ["source_hash"],
    )
    op.drop_constraint(
        "uq_yandex_market_ad_daily_stat",
        "yandex_market_ad_daily_stats",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_yandex_market_ad_daily_stat",
        "yandex_market_ad_daily_stats",
        ["stat_date", "source", "campaign_id"],
    )
