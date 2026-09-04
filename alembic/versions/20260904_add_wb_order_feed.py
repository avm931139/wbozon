"""add realtime WB order feed

Revision ID: 20260904_wb_order_feed
Revises: 20260901_ozon_fbo_recon
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_wb_order_feed"
down_revision = "20260901_ozon_fbo_recon"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_order_feed_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("srid", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id"), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("chrt_id", sa.BigInteger(), nullable=True),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cancel_type", sa.String(length=30), nullable=True),
        sa.Column("is_b2b", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_mp", sa.Boolean(), nullable=False),
        sa.Column("seller_price", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("warehouse_name", sa.String(), nullable=True),
        sa.Column("warehouse_region", sa.String(), nullable=True),
        sa.Column("destination_city", sa.String(), nullable=True),
        sa.Column("destination_district", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("srid", name="uq_wb_order_feed_orders_srid"),
    )
    for column in (
        "srid", "product_id", "nm_id", "chrt_id", "order_date", "status_updated_at",
        "status", "cancel_type", "is_b2b", "is_mp", "fetched_at",
    ):
        op.create_index(f"ix_wb_order_feed_orders_{column}", "wb_order_feed_orders", [column])

    op.create_table(
        "wb_order_feed_sync_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rows_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    for column in ("started_at", "finished_at", "status"):
        op.create_index(f"ix_wb_order_feed_sync_runs_{column}", "wb_order_feed_sync_runs", [column])


def downgrade() -> None:
    op.drop_table("wb_order_feed_sync_runs")
    op.drop_table("wb_order_feed_orders")
