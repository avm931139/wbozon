"""add Ozon documents and accounting storage

Revision ID: 20260831_ozon_accounting
Revises: 20260831_wb_document_files
"""

from alembic import op
import sqlalchemy as sa


revision = "20260831_ozon_accounting"
down_revision = "20260831_wb_document_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ozon_accounting_report_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("report_code", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_code", name="uq_ozon_accounting_report_requests_code"),
        sa.UniqueConstraint(
            "report_type",
            "period_start",
            name="uq_ozon_accounting_request_period",
        ),
    )
    for column in ("id", "report_type", "period_start", "report_code", "status", "requested_at"):
        op.create_index(
            f"ix_ozon_accounting_report_requests_{column}",
            "ozon_accounting_report_requests",
            [column],
        )

    op.create_table(
        "ozon_accounting_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("report_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_ozon_accounting_reports_code"),
    )
    for column in ("id", "code", "report_type", "status", "report_created_at"):
        op.create_index(
            f"ix_ozon_accounting_reports_{column}",
            "ozon_accounting_reports",
            [column],
        )

    op.create_table(
        "ozon_accounting_report_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("ozon_accounting_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("local_path", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_extension", sa.String(length=30), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", name="uq_ozon_accounting_report_files_report_id"),
    )
    for column in ("report_id", "file_extension", "file_sha256", "downloaded_at"):
        op.create_index(
            f"ix_ozon_accounting_report_files_{column}",
            "ozon_accounting_report_files",
            [column],
        )

    op.create_table(
        "ozon_accounting_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_type", sa.String(length=50), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "snapshot_type",
            "period_start",
            "period_end",
            name="uq_ozon_accounting_snapshot_period",
        ),
    )
    for column in ("id", "snapshot_type", "period_start", "period_end", "fetched_at"):
        op.create_index(
            f"ix_ozon_accounting_snapshots_{column}",
            "ozon_accounting_snapshots",
            [column],
        )


def downgrade() -> None:
    op.drop_table("ozon_accounting_snapshots")
    op.drop_table("ozon_accounting_report_files")
    op.drop_table("ozon_accounting_reports")
    op.drop_table("ozon_accounting_report_requests")
