"""add persistent WB synchronization logs

Revision ID: 20260809_wb_sync_logging
Revises: 20260809_promotion_finance
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_wb_sync_logging"
down_revision = "20260809_promotion_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_sync_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(20, 3), nullable=True),
        sa.Column("tasks_total", sa.Integer(), nullable=False),
        sa.Column("tasks_succeeded", sa.Integer(), nullable=False),
        sa.Column("tasks_failed", sa.Integer(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
    )
    for column in ("status", "started_at", "finished_at"):
        op.create_index(f"ix_wb_sync_runs_{column}", "wb_sync_runs", [column])

    op.create_table(
        "wb_sync_errors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.String(32), sa.ForeignKey("wb_sync_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("task", sa.String(100), nullable=True),
        sa.Column("phase", sa.String(50), nullable=False),
        sa.Column("exception_type", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("file", sa.Text(), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("function", sa.String(255), nullable=True),
        sa.Column("module", sa.String(255), nullable=True),
        sa.Column("source_line", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("cycle_id", "task", "phase", "exception_type", "created_at"):
        op.create_index(f"ix_wb_sync_errors_{column}", "wb_sync_errors", [column])


def downgrade() -> None:
    op.drop_table("wb_sync_errors")
    op.drop_table("wb_sync_runs")
