"""add financial report reconciliation journal

Revision ID: 20260907_fin_reconcile
Revises: 20260906_product_costs
"""

from alembic import op
import sqlalchemy as sa


revision = "20260907_fin_reconcile"
down_revision = "20260906_product_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_reconciliation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_file", sa.String(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("marketplace", sa.String(length=30), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cabinet_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_in_api", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_in_cabinet", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_mismatches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cabinet_total", sa.Numeric(20, 6), nullable=True),
        sa.Column("api_total", sa.Numeric(20, 6), nullable=True),
        sa.Column("difference", sa.Numeric(20, 6), nullable=True),
        sa.Column("report_path", sa.String(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("file_sha256", name="uq_finance_reconciliation_file_sha256"),
        comment="Сверки загруженных вручную финансовых отчётов с финансовыми данными API.",
    )
    for column in ("file_sha256", "marketplace", "period_start", "period_end", "status", "started_at"):
        op.create_index(f"ix_finance_reconciliation_runs_{column}", "finance_reconciliation_runs", [column])


def downgrade() -> None:
    op.drop_table("finance_reconciliation_runs")
