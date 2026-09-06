"""add marketplace current prices and immutable snapshots

Revision ID: 20260906_marketplace_prices
Revises: 20260906_yandex_market_ads
"""

from alembic import op
import sqlalchemy as sa


revision = "20260906_marketplace_prices"
down_revision = "20260906_yandex_market_ads"
branch_labels = None
depends_on = None


def price_columns() -> list[sa.Column]:
    return [
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("product_id", sa.String(), nullable=True),
        sa.Column("variant_id", sa.String(), nullable=True),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("list_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("seller_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("customer_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("club_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("min_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("discount_percent", sa.Numeric(12, 6), nullable=True),
        sa.Column("club_discount_percent", sa.Numeric(12, 6), nullable=True),
        sa.Column("in_promotion", sa.Boolean(), nullable=True),
        sa.Column("auto_action_enabled", sa.Boolean(), nullable=True),
        sa.Column("promotion_names", sa.JSON(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "marketplace_price_sync_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rows_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    for column in ("marketplace", "started_at", "status"):
        op.create_index(
            f"ix_marketplace_price_sync_runs_{column}",
            "marketplace_price_sync_runs",
            [column],
        )

    op.create_table(
        "marketplace_current_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        *price_columns(),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("marketplace", "source_key", name="uq_marketplace_current_price"),
    )
    op.create_table(
        "marketplace_price_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("marketplace_price_sync_runs.id"),
            nullable=False,
        ),
        *price_columns(),
        sa.UniqueConstraint(
            "marketplace", "source_key", "captured_at", name="uq_marketplace_price_snapshot"
        ),
    )
    indexes = ("marketplace", "account_id", "offer_id", "product_id", "variant_id", "in_promotion", "captured_at")
    for table in ("marketplace_current_prices", "marketplace_price_snapshots"):
        for column in indexes:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_marketplace_current_prices_active", "marketplace_current_prices", ["active"])
    op.create_index("ix_marketplace_price_snapshots_source_key", "marketplace_price_snapshots", ["source_key"])
    op.create_index("ix_marketplace_price_snapshots_run_id", "marketplace_price_snapshots", ["run_id"])


def downgrade() -> None:
    op.drop_table("marketplace_price_snapshots")
    op.drop_table("marketplace_current_prices")
    op.drop_table("marketplace_price_sync_runs")
