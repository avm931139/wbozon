"""add private operational notification queue

Revision ID: 20260831_operations_notify
Revises: 20260830_inventory_workers
"""

from alembic import op
import sqlalchemy as sa


revision = "20260831_operations_notify"
down_revision = "20260830_inventory_workers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_monitor_states",
        sa.Column("id", sa.String(length=30), primary_key=True),
        sa.Column("cursor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "operations_event_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=150), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("telegram_message_ids", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_key", name="uq_operations_event_delivery_key"),
        comment="Очередь личных Telegram-уведомлений о работе приложения.",
    )
    for column in (
        "event_key",
        "source_type",
        "source_id",
        "occurred_at",
        "severity",
        "status",
    ):
        op.create_index(
            f"ix_operations_event_deliveries_{column}",
            "operations_event_deliveries",
            [column],
        )
    op.create_table(
        "healthcheck_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("checks_total", sa.Integer(), nullable=False),
        sa.Column("checks_failed", sa.Integer(), nullable=False),
        sa.Column("failure_signature", sa.String(length=16), nullable=True),
        sa.Column("checks", sa.JSON(), nullable=False),
    )
    for column in ("checked_at", "status", "failure_signature"):
        op.create_index(f"ix_healthcheck_runs_{column}", "healthcheck_runs", [column])


def downgrade() -> None:
    op.drop_table("healthcheck_runs")
    op.drop_table("operations_event_deliveries")
    op.drop_table("operations_monitor_states")
