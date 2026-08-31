"""add local WB document files

Revision ID: 20260831_wb_document_files
Revises: 20260831_wb_documents
"""

from alembic import op
import sqlalchemy as sa


revision = "20260831_wb_document_files"
down_revision = "20260831_wb_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_document_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("wb_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extension", sa.String(length=30), nullable=False),
        sa.Column("local_path", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_id",
            "extension",
            name="uq_wb_document_file_document_extension",
        ),
        comment="Локальные файлы документов WB; один документ может иметь несколько форматов.",
    )
    for column in ("document_id", "extension", "file_sha256", "downloaded_at"):
        op.create_index(f"ix_wb_document_files_{column}", "wb_document_files", [column])


def downgrade() -> None:
    op.drop_table("wb_document_files")
