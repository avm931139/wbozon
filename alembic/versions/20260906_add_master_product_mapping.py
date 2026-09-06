"""add master products and marketplace offer links

Revision ID: 20260906_product_mapping
Revises: 20260906_marketplace_prices
"""

from alembic import op
import sqlalchemy as sa


revision = "20260906_product_mapping"
down_revision = "20260906_marketplace_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_mapping_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("master_products", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exact_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suffix_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inactive_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_product_mapping_runs_started_at", "product_mapping_runs", ["started_at"])
    op.create_index("ix_product_mapping_runs_status", "product_mapping_runs", ["status"])

    op.create_table(
        "master_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article", name="uq_master_products_article"),
    )
    op.create_index("ix_master_products_article", "master_products", ["article"])
    op.create_index("ix_master_products_active", "master_products", ["active"])

    op.create_table(
        "marketplace_product_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_product_id",
            sa.Integer(),
            sa.ForeignKey("master_products.id"),
            nullable=False,
        ),
        sa.Column("marketplace", sa.String(length=30), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("external_product_id", sa.String(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("source_article", sa.String(), nullable=False),
        sa.Column("normalized_article", sa.String(), nullable=False),
        sa.Column("match_method", sa.String(length=20), nullable=False),
        sa.Column("is_test_variant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "marketplace",
            "account_id",
            "external_product_id",
            name="uq_marketplace_product_link_source",
        ),
    )
    for column in (
        "master_product_id", "marketplace", "account_id", "external_product_id",
        "offer_id", "normalized_article", "match_method", "is_test_variant", "active",
    ):
        op.create_index(f"ix_marketplace_product_links_{column}", "marketplace_product_links", [column])

    for table in ("marketplace_current_prices", "marketplace_price_snapshots"):
        op.add_column(table, sa.Column("master_product_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_master_product_id",
            table,
            "master_products",
            ["master_product_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_master_product_id", table, ["master_product_id"])


def downgrade() -> None:
    for table in ("marketplace_price_snapshots", "marketplace_current_prices"):
        op.drop_index(f"ix_{table}_master_product_id", table_name=table)
        op.drop_constraint(f"fk_{table}_master_product_id", table, type_="foreignkey")
        op.drop_column(table, "master_product_id")
    op.drop_table("marketplace_product_links")
    op.drop_table("master_products")
    op.drop_table("product_mapping_runs")
