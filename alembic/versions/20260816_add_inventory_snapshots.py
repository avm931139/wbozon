"""add periodic inventory snapshots

Revision ID: 20260816_inventory_snapshots
Revises: 20260809_ozon_ads
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_inventory_snapshots"
down_revision = "20260809_ozon_ads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_sync_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_type", sa.String(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("wb_fbs_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wb_fbo_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ozon_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        comment="Журнал периодических загрузок и ежедневных срезов остатков.",
    )
    for column in ("run_type", "snapshot_date", "status"):
        op.create_index(f"ix_inventory_sync_runs_{column}", "inventory_sync_runs", [column])

    op.create_table(
        "wb_fbs_stock_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("size_id", sa.Integer(), sa.ForeignKey("wb_product_sizes.id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("wb_fbs_warehouses.id"), nullable=False),
        sa.Column("sku", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.UniqueConstraint("snapshot_date", "sku", "warehouse_id", name="uq_wb_fbs_stock_snapshot"),
        comment="Ежедневные срезы FBS-остатков Wildberries на 01:00 по Москве.",
    )
    for column in ("snapshot_date", "size_id", "warehouse_id", "sku"):
        op.create_index(f"ix_wb_fbs_stock_snapshots_{column}", "wb_fbs_stock_snapshots", [column])

    op.create_table(
        "wb_fbo_stock_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("size_id", sa.Integer(), sa.ForeignKey("wb_product_sizes.id"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("wb_fbo_warehouses.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_way_to_client", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_way_from_client", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.UniqueConstraint("snapshot_date", "size_id", "warehouse_id", name="uq_wb_fbo_stock_snapshot"),
        comment="Ежедневные срезы FBO-остатков Wildberries на 01:00 по Москве.",
    )
    for column in ("snapshot_date", "size_id", "warehouse_id"):
        op.create_index(f"ix_wb_fbo_stock_snapshots_{column}", "wb_fbo_stock_snapshots", [column])

    op.create_table(
        "ozon_stock_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("stock_type", sa.String(), nullable=False),
        sa.Column("present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("snapshot_date", "product_id", "stock_type", name="uq_ozon_stock_snapshot"),
        comment="Ежедневные срезы остатков Ozon на 01:00 по Москве.",
    )
    for column in ("snapshot_date", "product_id", "offer_id", "stock_type"):
        op.create_index(f"ix_ozon_stock_snapshots_{column}", "ozon_stock_snapshots", [column])


def downgrade() -> None:
    op.drop_table("ozon_stock_snapshots")
    op.drop_table("wb_fbo_stock_snapshots")
    op.drop_table("wb_fbs_stock_snapshots")
    op.drop_table("inventory_sync_runs")
