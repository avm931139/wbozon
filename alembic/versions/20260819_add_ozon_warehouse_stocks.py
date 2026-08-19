"""add warehouse-level Ozon inventory

Revision ID: 20260819_ozon_wh_stocks
Revises: 20260816_inventory_snapshots
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_ozon_wh_stocks"
down_revision = "20260816_inventory_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_sync_runs",
        sa.Column("ozon_warehouse_rows", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "ozon_warehouses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ozon_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("cluster_id", sa.BigInteger(), nullable=True),
        sa.Column("cluster_name", sa.String(), nullable=True),
        sa.Column("macrolocal_cluster_id", sa.BigInteger(), nullable=True),
        sa.Column("stock_types", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ozon_warehouse_id", name="uq_ozon_warehouses_ozon_warehouse_id"),
        comment="Справочник физических складов Ozon для остатков FBO/FBS.",
    )
    for column in ("ozon_warehouse_id", "cluster_id", "macrolocal_cluster_id"):
        op.create_index(f"ix_ozon_warehouses_{column}", "ozon_warehouses", [column])

    op.create_table(
        "ozon_warehouse_stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("ozon_warehouses.id"), nullable=False),
        sa.Column("stock_type", sa.String(), nullable=False),
        sa.Column("present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "product_id",
            "warehouse_id",
            "stock_type",
            name="uq_ozon_warehouse_stock_identity",
        ),
        comment="Текущие остатки Ozon в разрезе физического склада и схемы хранения.",
    )
    for column in ("product_id", "offer_id", "sku", "warehouse_id", "stock_type"):
        op.create_index(f"ix_ozon_warehouse_stocks_{column}", "ozon_warehouse_stocks", [column])

    op.create_table(
        "ozon_warehouse_stock_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("ozon_warehouses.id"), nullable=False),
        sa.Column("stock_type", sa.String(), nullable=False),
        sa.Column("present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_date",
            "product_id",
            "warehouse_id",
            "stock_type",
            name="uq_ozon_warehouse_stock_snapshot",
        ),
        comment="Ежедневные срезы складских остатков Ozon на 01:00 по Москве.",
    )
    for column in ("snapshot_date", "product_id", "offer_id", "sku", "warehouse_id", "stock_type"):
        op.create_index(
            f"ix_ozon_warehouse_stock_snapshots_{column}",
            "ozon_warehouse_stock_snapshots",
            [column],
        )


def downgrade() -> None:
    op.drop_table("ozon_warehouse_stock_snapshots")
    op.drop_table("ozon_warehouse_stocks")
    op.drop_table("ozon_warehouses")
    op.drop_column("inventory_sync_runs", "ozon_warehouse_rows")
