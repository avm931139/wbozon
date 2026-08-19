"""add financial sales and acquiring reports

Revision ID: 20260809_add_financial_reports
Revises: 20260809_add_fbw_supplies
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_add_financial_reports"
down_revision = "20260809_add_fbw_supplies"
branch_labels = None
depends_on = None


def _indexes(table: str, columns: tuple[str, ...], unique: tuple[str, ...] = ()) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column], unique=column in unique)


def upgrade() -> None:
    money = sa.Numeric(20, 6)
    op.create_table("wb_financial_sales_reports",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("report_wb_id", sa.BigInteger(), nullable=False),
        sa.Column("seller_finance_name", sa.String()), sa.Column("date_from", sa.DateTime(timezone=True), nullable=False), sa.Column("date_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("create_date", sa.DateTime(timezone=True), nullable=False), sa.Column("currency", sa.String(), nullable=False), sa.Column("report_type", sa.Integer(), nullable=False),
        sa.Column("retail_amount_sum", money, nullable=False), sa.Column("for_pay_sum", money, nullable=False), sa.Column("delivery_service_sum", money, nullable=False),
        sa.Column("paid_storage_sum", money, nullable=False), sa.Column("paid_acceptance_sum", money, nullable=False), sa.Column("deduction_sum", money, nullable=False),
        sa.Column("penalty_sum", money, nullable=False), sa.Column("additional_payment_sum", money, nullable=False), sa.Column("bank_payment_sum", money, nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("details_synced_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    _indexes("wb_financial_sales_reports", ("id", "report_wb_id", "date_from", "date_to", "create_date", "report_type"), ("report_wb_id",))

    op.create_table("wb_financial_sales_rows",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("report_id", sa.Integer(), sa.ForeignKey("wb_financial_sales_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rrd_id", sa.BigInteger(), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id")), sa.Column("nm_id", sa.BigInteger()),
        sa.Column("order_id", sa.BigInteger()), sa.Column("order_uid", sa.String()), sa.Column("srid", sa.String()), sa.Column("shk_id", sa.BigInteger()), sa.Column("sku", sa.String()),
        sa.Column("vendor_code", sa.String()), sa.Column("title", sa.String()), sa.Column("subject_name", sa.String()), sa.Column("brand_name", sa.String()), sa.Column("tech_size", sa.String()),
        sa.Column("seller_operation_name", sa.String()), sa.Column("order_date", sa.DateTime(timezone=True)), sa.Column("sale_date", sa.DateTime(timezone=True)), sa.Column("rr_date", sa.DateTime(timezone=True)),
        sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("retail_price", money, nullable=False), sa.Column("retail_amount", money, nullable=False),
        sa.Column("retail_price_with_discount", money, nullable=False), sa.Column("for_pay", money, nullable=False), sa.Column("delivery_service", money, nullable=False),
        sa.Column("acquiring_fee", money, nullable=False), sa.Column("ppvz_sales_commission", money, nullable=False), sa.Column("ppvz_reward", money, nullable=False),
        sa.Column("penalty", money, nullable=False), sa.Column("additional_payment", money, nullable=False), sa.Column("rebill_logistic_cost", money, nullable=False),
        sa.Column("paid_storage", money, nullable=False), sa.Column("deduction", money, nullable=False), sa.Column("paid_acceptance", money, nullable=False),
        sa.Column("currency", sa.String()), sa.Column("raw_data", sa.JSON(), nullable=False))
    _indexes("wb_financial_sales_rows", ("id", "report_id", "rrd_id", "product_id", "nm_id", "order_id", "order_uid", "srid", "sku", "seller_operation_name", "order_date", "sale_date", "rr_date"), ("rrd_id",))

    op.create_table("wb_financial_acquiring_reports",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("report_wb_id", sa.BigInteger(), nullable=False), sa.Column("seller_finance_name", sa.String()),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=False), sa.Column("date_to", sa.DateTime(timezone=True), nullable=False), sa.Column("create_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(), nullable=False), sa.Column("acquiring_fee_sum", money, nullable=False), sa.Column("acquiring_fee_vat_sum", money, nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("details_synced_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    _indexes("wb_financial_acquiring_reports", ("id", "report_wb_id", "date_from", "date_to", "create_date"), ("report_wb_id",))

    op.create_table("wb_financial_acquiring_rows",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("report_id", sa.Integer(), sa.ForeignKey("wb_financial_acquiring_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rrd_id", sa.BigInteger(), nullable=False), sa.Column("nm_id", sa.BigInteger()), sa.Column("srid", sa.String()), sa.Column("shk_id", sa.BigInteger()),
        sa.Column("acquiring_bank", sa.String()), sa.Column("document_type", sa.String()), sa.Column("invoice_number", sa.String()), sa.Column("currency", sa.String()),
        sa.Column("retail_amount", money, nullable=False), sa.Column("acquiring_fee", money, nullable=False), sa.Column("acquiring_fee_vat", money, nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True)), sa.Column("sale_date", sa.DateTime(timezone=True)), sa.Column("invoice_date", sa.DateTime(timezone=True)), sa.Column("raw_data", sa.JSON(), nullable=False))
    _indexes("wb_financial_acquiring_rows", ("id", "report_id", "rrd_id", "nm_id", "srid", "transaction_date", "sale_date"), ("rrd_id",))


def downgrade() -> None:
    for table in ("wb_financial_acquiring_rows", "wb_financial_acquiring_reports", "wb_financial_sales_rows", "wb_financial_sales_reports"):
        op.drop_table(table)
