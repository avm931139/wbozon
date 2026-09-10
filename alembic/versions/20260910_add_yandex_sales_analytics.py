"""Add Yandex Market cabinet sales analytics."""

from alembic import op
import sqlalchemy as sa


revision = "20260910_yandex_sales_analytics"
down_revision = "20260908_wb_sales_funnel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wb_sales_funnel_daily",
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "wb_sales_funnel_daily",
        sa.Column("cart_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "yandex_market_sales_analytics_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("offer_name", sa.String(), nullable=True),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("brand_name", sa.String(), nullable=True),
        sa.Column("shows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("to_cart", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_items_amount", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("delivered_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_amount", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("delivered_from_ordered_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_from_ordered_amount", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("cancelled_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("returned_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "business_id", "stat_date", "offer_id",
            name="uq_yandex_market_sales_analytics_daily",
        ),
    )
    for name in ("business_id", "stat_date", "offer_id", "fetched_at"):
        op.create_index(
            f"ix_yandex_market_sales_analytics_daily_{name}",
            "yandex_market_sales_analytics_daily",
            [name],
        )


def downgrade() -> None:
    op.drop_table("yandex_market_sales_analytics_daily")
    op.drop_column("wb_sales_funnel_daily", "cart_count")
    op.drop_column("wb_sales_funnel_daily", "open_count")
