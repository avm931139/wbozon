"""wb integration

Revision ID: 20240809_wb_integration
Revises: 
Create Date: 2026-08-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "20240809_wb_integration"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["wb_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wb_categories_id"), "wb_categories", ["id"], unique=False)
    op.create_index(op.f("ix_wb_categories_wb_id"), "wb_categories", ["wb_id"], unique=False)
    op.create_unique_constraint("uq_wb_categories_wb_id", "wb_categories", ["wb_id"])

    op.create_table(
        "wb_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.String(), nullable=False),
        sa.Column("nm_id", sa.String(), nullable=True),
        sa.Column("vendor_code", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["wb_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wb_products_id"), "wb_products", ["id"], unique=False)
    op.create_index(op.f("ix_wb_products_wb_id"), "wb_products", ["wb_id"], unique=False)
    op.create_index(op.f("ix_wb_products_nm_id"), "wb_products", ["nm_id"], unique=True)
    op.create_index(op.f("ix_wb_products_vendor_code"), "wb_products", ["vendor_code"], unique=False)
    op.create_unique_constraint("uq_wb_products_wb_id", "wb_products", ["wb_id"])

    op.create_table(
        "wb_warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("warehouse_type", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wb_warehouses_id"), "wb_warehouses", ["id"], unique=False)
    op.create_index(op.f("ix_wb_warehouses_wb_id"), "wb_warehouses", ["wb_id"], unique=False)
    op.create_unique_constraint("uq_wb_warehouses_wb_id", "wb_warehouses", ["wb_id"])

    op.create_table(
        "wb_stocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["wb_products.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["wb_warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wb_stocks_id"), "wb_stocks", ["id"], unique=False)
    op.create_index(op.f("ix_wb_stocks_product_id"), "wb_stocks", ["product_id"], unique=False)
    op.create_index(op.f("ix_wb_stocks_warehouse_id"), "wb_stocks", ["warehouse_id"], unique=False)
    op.create_unique_constraint("uq_wb_stocks_product_warehouse", "wb_stocks", ["product_id", "warehouse_id"])


def downgrade() -> None:
    op.drop_table("wb_stocks")
    op.drop_table("wb_warehouses")
    op.drop_table("wb_products")
    op.drop_table("wb_categories")
