"""Add cabinet-wide WB Sales Funnel audit totals."""

from alembic import op
import sqlalchemy as sa


revision = "20260911_wb_funnel_account"
down_revision = "20260910_yandex_sales_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_sales_funnel_account_daily",
        sa.Column("stat_date", sa.Date(), primary_key=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cart_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("buyout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyout_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_wb_sales_funnel_account_daily_fetched_at",
        "wb_sales_funnel_account_daily", ["fetched_at"],
    )


def downgrade() -> None:
    op.drop_table("wb_sales_funnel_account_daily")
