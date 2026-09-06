"""add normalized product catalog media, attributes and snapshots

Revision ID: 20260906_catalog_media
Revises: 20260906_product_mapping
"""

from alembic import op
import sqlalchemy as sa


revision = "20260906_catalog_media"
down_revision = "20260906_product_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_catalog_sync_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("media_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attribute_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshots_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_downloaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_existing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_product_catalog_sync_runs_started_at", "product_catalog_sync_runs", ["started_at"])
    op.create_index("ix_product_catalog_sync_runs_status", "product_catalog_sync_runs", ["status"])

    op.create_table(
        "marketplace_product_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id"), nullable=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("external_product_id", sa.String(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("file_extension", sa.String(length=20), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("download_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("download_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_error", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "external_product_id", "source_key", name="uq_marketplace_product_media_source"),
    )
    media_indexes = (
        "master_product_id", "marketplace", "account_id", "external_product_id", "offer_id",
        "media_type", "role", "file_sha256", "download_status", "active", "last_seen_at",
    )
    for column in media_indexes:
        op.create_index(f"ix_marketplace_product_media_{column}", "marketplace_product_media", [column])

    op.create_table(
        "marketplace_product_attributes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id"), nullable=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("external_product_id", sa.String(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "external_product_id", "source_key", name="uq_marketplace_product_attribute_source"),
    )
    for column in ("master_product_id", "marketplace", "account_id", "external_product_id", "offer_id", "name", "active", "last_seen_at"):
        op.create_index(f"ix_marketplace_product_attributes_{column}", "marketplace_product_attributes", [column])

    op.create_table(
        "marketplace_product_catalog_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("product_catalog_sync_runs.id"), nullable=False),
        sa.Column("master_product_id", sa.Integer(), sa.ForeignKey("master_products.id"), nullable=True),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("external_product_id", sa.String(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", "external_product_id", "content_hash", name="uq_marketplace_product_catalog_snapshot_hash"),
    )
    for column in ("run_id", "master_product_id", "marketplace", "account_id", "external_product_id", "offer_id", "content_hash", "captured_at"):
        op.create_index(f"ix_marketplace_product_catalog_snapshots_{column}", "marketplace_product_catalog_snapshots", [column])


def downgrade() -> None:
    op.drop_table("marketplace_product_catalog_snapshots")
    op.drop_table("marketplace_product_attributes")
    op.drop_table("marketplace_product_media")
    op.drop_table("product_catalog_sync_runs")
