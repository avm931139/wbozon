"""add independent Ozon task run journal

Revision ID: 20260820_ozon_sync_runs
Revises: 20260819_ozon_wh_stocks
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_ozon_sync_runs"
down_revision = "20260819_ozon_wh_stocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ozon_sync_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        comment="Журнал независимых заданий синхронизации Ozon.",
    )
    op.create_index("ix_ozon_sync_runs_task", "ozon_sync_runs", ["task"])
    op.create_index("ix_ozon_sync_runs_started_at", "ozon_sync_runs", ["started_at"])
    op.create_index("ix_ozon_sync_runs_status", "ozon_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ozon_sync_runs_status", table_name="ozon_sync_runs")
    op.drop_index("ix_ozon_sync_runs_started_at", table_name="ozon_sync_runs")
    op.drop_index("ix_ozon_sync_runs_task", table_name="ozon_sync_runs")
    op.drop_table("ozon_sync_runs")
