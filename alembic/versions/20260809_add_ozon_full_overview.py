"""add complete Ozon operational and reporting data

Revision ID: 20260809_ozon_overview
Revises: 20260809_ozon_core
"""
from alembic import op
import sqlalchemy as sa

revision = "20260809_ozon_overview"
down_revision = "20260809_ozon_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("ozon_supplies",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("supply_order_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("supply_order_number", sa.String()), sa.Column("state", sa.String()), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("supply_date_from", sa.DateTime(timezone=True)), sa.Column("supply_date_to", sa.DateTime(timezone=True)),
        sa.Column("warehouse_id", sa.BigInteger()), sa.Column("warehouse_name", sa.String()),
        sa.Column("total_items_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("total_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items", sa.JSON(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("ozon_questions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("question_id", sa.String(), nullable=False, unique=True), sa.Column("sku", sa.BigInteger()),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("status", sa.String()), sa.Column("is_answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("answers", sa.JSON(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("ozon_reviews",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("review_id", sa.String(), nullable=False, unique=True), sa.Column("sku", sa.BigInteger()),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("rating", sa.Integer()), sa.Column("status", sa.String()), sa.Column("is_answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("comments", sa.JSON(), nullable=False), sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("ozon_daily_sales",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("sale_date", sa.Date(), nullable=False), sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.String()), sa.Column("offer_id", sa.String()), sa.Column("ordered_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_units", sa.Integer(), nullable=False, server_default="0"), sa.Column("returns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancellations", sa.Integer(), nullable=False, server_default="0"), sa.Column("revenue", sa.Numeric(20,6), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sale_date", "sku", name="uq_ozon_daily_sale_date_sku"))
    op.create_table("ozon_finance_accruals",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("accrual_date", sa.Date(), nullable=False), sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("accrual_type", sa.String(), nullable=False), sa.Column("accrual_name", sa.String()), sa.Column("posting_number", sa.String()),
        sa.Column("amount", sa.Numeric(20,6), nullable=False, server_default="0"), sa.Column("currency", sa.String()), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("accrual_date", "operation_id", "accrual_type", name="uq_ozon_finance_accrual"))
    indexes = {"ozon_supplies": ["supply_order_id","supply_order_number","state","created_at","warehouse_id"],
               "ozon_questions": ["question_id","sku","status","is_answered","created_at"],
               "ozon_reviews": ["review_id","sku","rating","status","is_answered","created_at"],
               "ozon_daily_sales": ["sale_date","sku","offer_id"],
               "ozon_finance_accruals": ["accrual_date","operation_id","accrual_type","posting_number"]}
    for table, columns in indexes.items():
        for column in columns: op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ("ozon_finance_accruals", "ozon_daily_sales", "ozon_reviews", "ozon_questions", "ozon_supplies"):
        op.drop_table(table)
