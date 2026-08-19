"""store WB stock by SKU and warehouse

Revision ID: 20260809_add_stock_sku
Revises: 20260809_normalize_wb_catalog
Create Date: 2026-08-09 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_add_stock_sku"
down_revision = "20260809_normalize_wb_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wb_stocks", sa.Column("sku", sa.String(), nullable=True))
    op.drop_constraint("uq_wb_stocks_size_warehouse", "wb_stocks", type_="unique")
    op.create_index("ix_wb_stocks_sku", "wb_stocks", ["sku"])
    op.create_unique_constraint("uq_wb_stocks_sku_warehouse", "wb_stocks", ["sku", "warehouse_id"])
    op.alter_column("wb_stocks", "sku", nullable=False)


def downgrade() -> None:
    op.alter_column("wb_stocks", "sku", nullable=True)
    op.drop_constraint("uq_wb_stocks_sku_warehouse", "wb_stocks", type_="unique")
    op.drop_index("ix_wb_stocks_sku", table_name="wb_stocks")
    op.create_unique_constraint("uq_wb_stocks_size_warehouse", "wb_stocks", ["size_id", "warehouse_id"])
    op.drop_column("wb_stocks", "sku")
