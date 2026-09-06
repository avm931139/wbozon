"""add initial product cost records

Revision ID: 20260906_product_costs
Revises: 20260906_catalog_media
"""

from alembic import op
import sqlalchemy as sa


revision = "20260906_product_costs"
down_revision = "20260906_catalog_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_cost_import_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_file", sa.String(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped_blank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_product_cost_import_runs_source_sha256",
        "product_cost_import_runs",
        ["source_sha256"],
        unique=True,
    )
    op.create_index("ix_product_cost_import_runs_started_at", "product_cost_import_runs", ["started_at"])
    op.create_index("ix_product_cost_import_runs_status", "product_cost_import_runs", ["status"])

    op.create_table(
        "product_cost_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "import_run_id",
            sa.String(),
            sa.ForeignKey("product_cost_import_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "master_product_id",
            sa.Integer(),
            sa.ForeignKey("master_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("article", sa.String(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(20, 6), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="RUB"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "import_run_id", "master_product_id", name="uq_product_cost_record_import_product"
        ),
    )
    op.create_index("ix_product_cost_records_import_run_id", "product_cost_records", ["import_run_id"])
    op.create_index("ix_product_cost_records_master_product_id", "product_cost_records", ["master_product_id"])
    op.create_index("ix_product_cost_records_article", "product_cost_records", ["article"])
    op.create_index("ix_product_cost_records_effective_at", "product_cost_records", ["effective_at"])


def downgrade() -> None:
    op.drop_table("product_cost_records")
    op.drop_table("product_cost_import_runs")
