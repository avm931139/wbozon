"""add FBW supply history

Revision ID: 20260809_add_fbw_supplies
Revises: 20260809_add_fbs_fbo_orders
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_add_fbw_supplies"
down_revision = "20260809_add_fbs_fbo_orders"
branch_labels = None
depends_on = None


def _indexes(table: str, columns: tuple[str, ...], unique: tuple[str, ...] = ()) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column], unique=column in unique)


def upgrade() -> None:
    op.create_table("wb_fbw_warehouses",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("wb_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False), sa.Column("address", sa.Text()), sa.Column("work_time", sa.String()),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_transit_active", sa.Boolean(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    _indexes("wb_fbw_warehouses", ("id", "wb_id"), ("wb_id",))

    op.create_table("wb_fbw_supplies",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("supply_wb_id", sa.BigInteger()), sa.Column("preorder_wb_id", sa.BigInteger()),
        sa.Column("status_id", sa.Integer(), nullable=False), sa.Column("box_type_id", sa.Integer()), sa.Column("virtual_type_id", sa.Integer()), sa.Column("is_box_on_pallet", sa.Boolean()),
        sa.Column("create_date", sa.DateTime(timezone=True), nullable=False), sa.Column("supply_date", sa.DateTime(timezone=True)), sa.Column("fact_date", sa.DateTime(timezone=True)), sa.Column("source_updated_date", sa.DateTime(timezone=True)),
        sa.Column("warehouse_wb_id", sa.BigInteger()), sa.Column("warehouse_name", sa.String()), sa.Column("actual_warehouse_wb_id", sa.BigInteger()), sa.Column("actual_warehouse_name", sa.String()),
        sa.Column("transit_warehouse_wb_id", sa.BigInteger()), sa.Column("transit_warehouse_name", sa.String()), sa.Column("acceptance_cost", sa.Float()),
        sa.Column("paid_acceptance_coefficient", sa.Float()), sa.Column("storage_coefficient", sa.String()), sa.Column("delivery_coefficient", sa.String()),
        sa.Column("reject_reason", sa.Text()), sa.Column("supplier_assign_name", sa.String()), sa.Column("quantity", sa.Integer()),
        sa.Column("accepted_quantity", sa.Integer()), sa.Column("ready_for_sale_quantity", sa.Integer()), sa.Column("unloading_quantity", sa.Integer()), sa.Column("depersonalized_quantity", sa.Integer()),
        sa.Column("can_show_quantity", sa.Boolean()), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    _indexes("wb_fbw_supplies", ("id", "supply_wb_id", "preorder_wb_id", "status_id", "create_date", "supply_date", "fact_date", "source_updated_date", "warehouse_wb_id"), ("supply_wb_id", "preorder_wb_id"))

    op.create_table("wb_fbw_supply_goods",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("supply_id", sa.Integer(), sa.ForeignKey("wb_fbw_supplies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id")), sa.Column("size_id", sa.Integer(), sa.ForeignKey("wb_product_sizes.id")),
        sa.Column("nm_id", sa.BigInteger(), nullable=False), sa.Column("barcode", sa.String(), nullable=False), sa.Column("vendor_code", sa.String()),
        sa.Column("tech_size", sa.String()), sa.Column("color", sa.String()), sa.Column("tnved", sa.String()), sa.Column("need_kiz", sa.Boolean(), nullable=False),
        sa.Column("supplier_box_amount", sa.Integer()), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("accepted_quantity", sa.Integer(), nullable=False),
        sa.Column("ready_for_sale_quantity", sa.Integer(), nullable=False), sa.Column("unloading_quantity", sa.Integer(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("supply_id", "barcode", name="uq_wb_fbw_supply_good_barcode"))
    _indexes("wb_fbw_supply_goods", ("id", "supply_id", "product_id", "size_id", "nm_id", "barcode"))

    op.create_table("wb_fbw_supply_packages",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("supply_id", sa.Integer(), sa.ForeignKey("wb_fbw_supplies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_code", sa.String(), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("supply_id", "package_code", name="uq_wb_fbw_supply_package_code"))
    _indexes("wb_fbw_supply_packages", ("id", "supply_id", "package_code"))

    op.create_table("wb_fbw_supply_package_goods",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("package_id", sa.Integer(), sa.ForeignKey("wb_fbw_supply_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("barcode", sa.String(), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("package_id", "barcode", name="uq_wb_fbw_package_good_barcode"))
    _indexes("wb_fbw_supply_package_goods", ("id", "package_id", "barcode"))

    op.create_table("wb_fbw_supply_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("supply_id", sa.Integer(), sa.ForeignKey("wb_fbw_supplies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_updated_date", sa.DateTime(timezone=True), nullable=False), sa.Column("status_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer()), sa.Column("accepted_quantity", sa.Integer()), sa.Column("ready_for_sale_quantity", sa.Integer()),
        sa.Column("unloading_quantity", sa.Integer()), sa.Column("depersonalized_quantity", sa.Integer()), sa.Column("fetched_at", sa.DateTime(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("supply_id", "source_updated_date", name="uq_wb_fbw_supply_snapshot_version"))
    _indexes("wb_fbw_supply_snapshots", ("id", "supply_id"))


def downgrade() -> None:
    for table in ("wb_fbw_supply_snapshots", "wb_fbw_supply_package_goods", "wb_fbw_supply_packages", "wb_fbw_supply_goods", "wb_fbw_supplies", "wb_fbw_warehouses"):
        op.drop_table(table)
