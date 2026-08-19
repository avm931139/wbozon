"""split FBS and FBO inventory

Revision ID: 20260809_split_fbs_fbo
Revises: 20260809_add_stock_sku
Create Date: 2026-08-09 00:00:02.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_split_fbs_fbo"
down_revision = "20260809_add_stock_sku"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_fbs_warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("office_id", sa.BigInteger(), nullable=True),
        sa.Column("cargo_type", sa.Integer(), nullable=True),
        sa.Column("delivery_type", sa.Integer(), nullable=True),
        sa.Column("is_deleting", sa.Boolean(), nullable=True),
        sa.Column("is_processing", sa.Boolean(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wb_id", name="uq_wb_fbs_warehouses_wb_id"),
    )
    op.create_index("ix_wb_fbs_warehouses_id", "wb_fbs_warehouses", ["id"])
    op.create_index("ix_wb_fbs_warehouses_wb_id", "wb_fbs_warehouses", ["wb_id"])

    op.create_table(
        "wb_fbs_stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("size_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["size_id"], ["wb_product_sizes.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["wb_fbs_warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", "warehouse_id", name="uq_wb_fbs_stocks_sku_warehouse"),
    )
    op.create_index("ix_wb_fbs_stocks_id", "wb_fbs_stocks", ["id"])
    op.create_index("ix_wb_fbs_stocks_size_id", "wb_fbs_stocks", ["size_id"])
    op.create_index("ix_wb_fbs_stocks_warehouse_id", "wb_fbs_stocks", ["warehouse_id"])
    op.create_index("ix_wb_fbs_stocks_sku", "wb_fbs_stocks", ["sku"])

    op.execute(sa.text("""
        INSERT INTO wb_fbs_warehouses
            (id, wb_id, name, office_id, cargo_type, delivery_type, is_deleting,
             is_processing, raw_data, created_at, updated_at)
        SELECT id, wb_id, name, office_id, cargo_type, delivery_type, is_deleting,
               is_processing, raw_data, created_at, updated_at
        FROM wb_warehouses
    """))
    op.execute(sa.text("""
        INSERT INTO wb_fbs_stocks
            (id, size_id, warehouse_id, sku, quantity, raw_data, created_at, updated_at)
        SELECT id, size_id, warehouse_id, sku, quantity, raw_data, created_at, updated_at
        FROM wb_stocks
    """))
    op.execute(sa.text("SELECT setval(pg_get_serial_sequence('wb_fbs_warehouses', 'id'), COALESCE(MAX(id), 1), true) FROM wb_fbs_warehouses"))
    op.execute(sa.text("SELECT setval(pg_get_serial_sequence('wb_fbs_stocks', 'id'), COALESCE(MAX(id), 1), true) FROM wb_fbs_stocks"))

    op.create_table(
        "wb_fbo_warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("region_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wb_id", "name", "region_name", name="uq_wb_fbo_warehouse_identity"),
    )
    op.create_index("ix_wb_fbo_warehouses_id", "wb_fbo_warehouses", ["id"])
    op.create_index("ix_wb_fbo_warehouses_wb_id", "wb_fbo_warehouses", ["wb_id"])

    op.create_table(
        "wb_fbo_stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("size_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("in_way_to_client", sa.Integer(), nullable=False),
        sa.Column("in_way_from_client", sa.Integer(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["size_id"], ["wb_product_sizes.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["wb_fbo_warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("size_id", "warehouse_id", name="uq_wb_fbo_stocks_size_warehouse"),
    )
    op.create_index("ix_wb_fbo_stocks_id", "wb_fbo_stocks", ["id"])
    op.create_index("ix_wb_fbo_stocks_size_id", "wb_fbo_stocks", ["size_id"])
    op.create_index("ix_wb_fbo_stocks_warehouse_id", "wb_fbo_stocks", ["warehouse_id"])

    op.drop_table("wb_stocks")
    op.drop_table("wb_warehouses")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is unsupported after separating FBS and FBO inventory")
