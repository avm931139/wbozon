"""add WB documents and balance snapshots

Revision ID: 20260831_wb_documents
Revises: 20260831_operations_notify
"""

from alembic import op
import sqlalchemy as sa


revision = "20260831_wb_documents"
down_revision = "20260831_operations_notify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_finance_balance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("current", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("for_withdraw", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
    )
    for column in ("id", "fetched_at", "currency"):
        op.create_index(
            f"ix_wb_finance_balance_snapshots_{column}",
            "wb_finance_balance_snapshots",
            [column],
        )
    op.create_table(
        "wb_document_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_wb_document_categories_name"),
    )
    for column in ("id", "name"):
        op.create_index(f"ix_wb_document_categories_{column}", "wb_document_categories", [column])
    op.create_table(
        "wb_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("extensions", sa.JSON(), nullable=False),
        sa.Column("document_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed", sa.Boolean(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("service_name", name="uq_wb_documents_service_name"),
    )
    for column in ("id", "service_name", "category", "document_created_at", "viewed"):
        op.create_index(f"ix_wb_documents_{column}", "wb_documents", [column])
    op.create_table(
        "wb_document_sync_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        comment="Журнал независимой синхронизации документов и баланса WB.",
    )
    for column in ("started_at", "finished_at", "status"):
        op.create_index(f"ix_wb_document_sync_runs_{column}", "wb_document_sync_runs", [column])


def downgrade() -> None:
    op.drop_table("wb_document_sync_runs")
    op.drop_table("wb_documents")
    op.drop_table("wb_document_categories")
    op.drop_table("wb_finance_balance_snapshots")
