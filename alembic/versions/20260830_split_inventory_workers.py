"""split inventory synchronization by marketplace

Revision ID: 20260830_inventory_workers
Revises: 20260830_yandex_stocks
"""

from alembic import op
import sqlalchemy as sa


revision = "20260830_inventory_workers"
down_revision = "20260830_yandex_stocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_sync_runs",
        sa.Column("marketplace", sa.String(), nullable=False, server_default="all"),
    )
    op.create_index(
        "ix_inventory_sync_runs_marketplace",
        "inventory_sync_runs",
        ["marketplace"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_sync_runs_marketplace", table_name="inventory_sync_runs")
    op.drop_column("inventory_sync_runs", "marketplace")
