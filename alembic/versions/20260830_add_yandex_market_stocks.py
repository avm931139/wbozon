"""add Yandex Market inventory

Revision ID: 20260830_yandex_stocks
Revises: 20260820_ozon_sync_runs
"""

from alembic import op
import sqlalchemy as sa


revision = "20260830_yandex_stocks"
down_revision = "20260820_ozon_sync_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_sync_runs",
        sa.Column("yandex_market_rows", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "yandex_market_stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("stock_type", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "campaign_id",
            "warehouse_id",
            "offer_id",
            "stock_type",
            name="uq_yandex_market_stock_identity",
        ),
        comment="Текущие остатки Яндекс Маркета по магазину, складу, SKU и типу.",
    )
    for column in ("campaign_id", "warehouse_id", "offer_id", "stock_type"):
        op.create_index(
            f"ix_yandex_market_stocks_{column}",
            "yandex_market_stocks",
            [column],
        )

    op.create_table(
        "yandex_market_stock_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("stock_type", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_date",
            "campaign_id",
            "warehouse_id",
            "offer_id",
            "stock_type",
            name="uq_yandex_market_stock_snapshot",
        ),
        comment="Ежедневные срезы остатков Яндекс Маркета на 00:00 по Москве.",
    )
    for column in (
        "snapshot_date",
        "campaign_id",
        "warehouse_id",
        "offer_id",
        "stock_type",
    ):
        op.create_index(
            f"ix_yandex_market_stock_snapshots_{column}",
            "yandex_market_stock_snapshots",
            [column],
        )


def downgrade() -> None:
    op.drop_table("yandex_market_stock_snapshots")
    op.drop_table("yandex_market_stocks")
    op.drop_column("inventory_sync_runs", "yandex_market_rows")
