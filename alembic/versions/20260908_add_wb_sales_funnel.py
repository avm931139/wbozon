"""Add preliminary Wildberries Sales Funnel history."""

from alembic import op
import sqlalchemy as sa


revision = "20260908_wb_sales_funnel"
down_revision = "20260907_yandex_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wb_sales_funnel_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("vendor_code", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("buyout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyout_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("cancel_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_sum", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stat_date", "nm_id", name="uq_wb_sales_funnel_daily_date_nm"),
    )
    for name in ("stat_date", "nm_id", "vendor_code", "fetched_at"):
        op.create_index(f"ix_wb_sales_funnel_daily_{name}", "wb_sales_funnel_daily", [name])
    op.create_table(
        "wb_sales_funnel_sync_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("rows_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    for name in ("started_at", "finished_at", "status"):
        op.create_index(f"ix_wb_sales_funnel_sync_runs_{name}", "wb_sales_funnel_sync_runs", [name])


def downgrade() -> None:
    op.drop_table("wb_sales_funnel_sync_runs")
    op.drop_table("wb_sales_funnel_daily")
