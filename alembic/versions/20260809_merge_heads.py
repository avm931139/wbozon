"""merge migration heads and align the initial schema

Revision ID: 20260809_merge_heads
Revises: 0001_initial, 20240809_wb_integration
Create Date: 2026-08-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_merge_heads"
down_revision = ("0001_initial", "20240809_wb_integration")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_wb_products_nm_id", table_name="wb_products")
    op.create_index("ix_wb_products_nm_id", "wb_products", ["nm_id"], unique=False)

    op.create_table(
        "example",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_example_id"), "example", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_example_id"), table_name="example")
    op.drop_table("example")

    op.drop_index("ix_wb_products_nm_id", table_name="wb_products")
    op.create_index("ix_wb_products_nm_id", "wb_products", ["nm_id"], unique=True)
