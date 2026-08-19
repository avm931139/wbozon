"""normalize WB catalog payload

Revision ID: 20260809_normalize_wb_catalog
Revises: 20260809_merge_heads
Create Date: 2026-08-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_normalize_wb_catalog"
down_revision = "20260809_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_subjects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wb_subjects_id", "wb_subjects", ["id"])
    op.create_index("ix_wb_subjects_wb_id", "wb_subjects", ["wb_id"], unique=True)

    op.drop_constraint("wb_products_category_id_fkey", "wb_products", type_="foreignkey")
    op.drop_column("wb_products", "category_id")
    op.drop_constraint("uq_wb_products_wb_id", "wb_products", type_="unique")
    op.drop_index("ix_wb_products_wb_id", table_name="wb_products")
    op.drop_column("wb_products", "wb_id")
    op.alter_column(
        "wb_products",
        "nm_id",
        existing_type=sa.String(),
        type_=sa.BigInteger(),
        postgresql_using="NULLIF(nm_id, '')::bigint",
        nullable=False,
    )
    op.drop_index("ix_wb_products_nm_id", table_name="wb_products")
    op.create_index("ix_wb_products_nm_id", "wb_products", ["nm_id"], unique=True)
    op.add_column("wb_products", sa.Column("imt_id", sa.BigInteger(), nullable=True))
    op.add_column("wb_products", sa.Column("nm_uuid", sa.String(length=36), nullable=True))
    op.add_column("wb_products", sa.Column("subject_id", sa.Integer(), nullable=True))
    op.add_column("wb_products", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("wb_products", sa.Column("need_kiz", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("wb_products", sa.Column("kiz_marked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("wb_products", sa.Column("wb_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("wb_products", sa.Column("wb_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("wb_products", sa.Column("documents", sa.JSON(), nullable=True))
    op.alter_column("wb_products", "need_kiz", server_default=None)
    op.alter_column("wb_products", "kiz_marked", server_default=None)
    op.create_index("ix_wb_products_imt_id", "wb_products", ["imt_id"])
    op.create_index("ix_wb_products_nm_uuid", "wb_products", ["nm_uuid"], unique=True)
    op.create_index("ix_wb_products_subject_id", "wb_products", ["subject_id"])
    op.create_index("ix_wb_products_brand", "wb_products", ["brand"])
    op.create_foreign_key(
        "fk_wb_products_subject_id",
        "wb_products",
        "wb_subjects",
        ["subject_id"],
        ["id"],
    )

    op.create_table(
        "wb_product_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("big_url", sa.Text(), nullable=True),
        sa.Column("c246x328_url", sa.Text(), nullable=True),
        sa.Column("c516x688_url", sa.Text(), nullable=True),
        sa.Column("hq_url", sa.Text(), nullable=True),
        sa.Column("square_url", sa.Text(), nullable=True),
        sa.Column("tm_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["wb_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "position", name="uq_wb_product_photo_position"),
    )
    op.create_index("ix_wb_product_photos_product_id", "wb_product_photos", ["product_id"])

    op.create_table(
        "wb_product_dimensions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("length", sa.Float(), nullable=True),
        sa.Column("weight_brutto", sa.Float(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["wb_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wb_product_dimensions_product_id", "wb_product_dimensions", ["product_id"], unique=True)

    op.create_table(
        "wb_characteristics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wb_characteristics_wb_id", "wb_characteristics", ["wb_id"], unique=True)

    op.create_table(
        "wb_product_characteristics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("characteristic_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["characteristic_id"], ["wb_characteristics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["wb_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "characteristic_id", name="uq_wb_product_characteristic"),
    )
    op.create_index("ix_wb_product_characteristics_product_id", "wb_product_characteristics", ["product_id"])
    op.create_index(
        "ix_wb_product_characteristics_characteristic_id",
        "wb_product_characteristics",
        ["characteristic_id"],
    )

    op.create_table(
        "wb_product_sizes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("chrt_id", sa.BigInteger(), nullable=False),
        sa.Column("tech_size", sa.String(), nullable=True),
        sa.Column("wb_size", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["wb_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wb_product_sizes_product_id", "wb_product_sizes", ["product_id"])
    op.create_index("ix_wb_product_sizes_chrt_id", "wb_product_sizes", ["chrt_id"], unique=True)

    op.create_table(
        "wb_size_barcodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("size_id", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["size_id"], ["wb_product_sizes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wb_size_barcodes_size_id", "wb_size_barcodes", ["size_id"])
    op.create_index("ix_wb_size_barcodes_barcode", "wb_size_barcodes", ["barcode"], unique=True)

    op.add_column("wb_warehouses", sa.Column("office_id", sa.BigInteger(), nullable=True))
    op.add_column("wb_warehouses", sa.Column("cargo_type", sa.Integer(), nullable=True))
    op.add_column("wb_warehouses", sa.Column("delivery_type", sa.Integer(), nullable=True))
    op.add_column("wb_warehouses", sa.Column("is_deleting", sa.Boolean(), nullable=True))
    op.add_column("wb_warehouses", sa.Column("is_processing", sa.Boolean(), nullable=True))
    op.drop_column("wb_warehouses", "warehouse_type")
    op.drop_column("wb_warehouses", "address")
    op.drop_column("wb_warehouses", "region")
    op.alter_column(
        "wb_warehouses",
        "wb_id",
        existing_type=sa.String(),
        type_=sa.BigInteger(),
        postgresql_using="wb_id::bigint",
        nullable=False,
    )

    op.drop_constraint("uq_wb_stocks_product_warehouse", "wb_stocks", type_="unique")
    op.drop_constraint("wb_stocks_product_id_fkey", "wb_stocks", type_="foreignkey")
    op.drop_index("ix_wb_stocks_product_id", table_name="wb_stocks")
    op.drop_column("wb_stocks", "product_id")
    op.add_column("wb_stocks", sa.Column("size_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_wb_stocks_size_id", "wb_stocks", "wb_product_sizes", ["size_id"], ["id"])
    op.create_index("ix_wb_stocks_size_id", "wb_stocks", ["size_id"])
    op.create_unique_constraint("uq_wb_stocks_size_warehouse", "wb_stocks", ["size_id", "warehouse_id"])
    op.alter_column("wb_stocks", "size_id", nullable=False)
    op.alter_column("wb_stocks", "quantity", existing_type=sa.Integer(), nullable=False, server_default="0")
    op.alter_column("wb_stocks", "quantity", server_default=None)

    op.drop_table("wb_categories")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is intentionally unsupported for the normalized WB catalog schema")
