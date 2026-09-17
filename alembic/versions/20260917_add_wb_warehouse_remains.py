"""Add full WB warehouse remains used by the dashboard.

Revision ID: 20260917_wb_warehouse_remains
Revises: 20260917_wb_funnel_periods
"""

from alembic import op
import sqlalchemy as sa


revision = "20260917_wb_warehouse_remains"
down_revision = "20260917_wb_funnel_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_warehouse_remains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vendor_code", sa.String(), nullable=False),
        sa.Column("warehouse_name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("vendor_code", "warehouse_name", name="uq_wb_warehouse_remain"),
        comment="Полные физические остатки WB из отчёта warehouse_remains.",
    )
    op.create_index("ix_wb_warehouse_remains_vendor_code", "wb_warehouse_remains", ["vendor_code"])
    op.create_index("ix_wb_warehouse_remains_warehouse_name", "wb_warehouse_remains", ["warehouse_name"])
    op.create_index("ix_wb_warehouse_remains_fetched_at", "wb_warehouse_remains", ["fetched_at"])
    op.create_table(
        "wb_warehouse_remain_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vendor_code", sa.String(), nullable=False),
        sa.Column("warehouse_name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_date", "vendor_code", "warehouse_name",
            name="uq_wb_warehouse_remain_snapshot",
        ),
        comment="Ежедневные срезы полных физических остатков WB.",
    )
    op.create_index(
        "ix_wb_warehouse_remain_snapshots_snapshot_date",
        "wb_warehouse_remain_snapshots", ["snapshot_date"],
    )
    op.create_index(
        "ix_wb_warehouse_remain_snapshots_vendor_code",
        "wb_warehouse_remain_snapshots", ["vendor_code"],
    )
    op.create_index(
        "ix_wb_warehouse_remain_snapshots_warehouse_name",
        "wb_warehouse_remain_snapshots", ["warehouse_name"],
    )
    op.add_column(
        "inventory_sync_runs",
        sa.Column("wb_warehouse_remains_rows", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("inventory_sync_runs", "wb_warehouse_remains_rows")
    op.drop_table("wb_warehouse_remain_snapshots")
    op.drop_table("wb_warehouse_remains")
