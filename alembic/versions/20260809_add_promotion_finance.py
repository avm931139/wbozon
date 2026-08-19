"""add WB Promotion account finance snapshots and campaign budgets

Revision ID: 20260809_promotion_finance
Revises: 20260809_advert_unique_cleanup
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_promotion_finance"
down_revision = "20260809_advert_unique_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    money = sa.Numeric(20, 6)
    op.add_column("wb_advert_campaigns", sa.Column("budget_cash", money, nullable=True))
    op.add_column("wb_advert_campaigns", sa.Column("budget_netting", money, nullable=True))
    op.add_column("wb_advert_campaigns", sa.Column("budget_total", money, nullable=True))
    op.add_column("wb_advert_campaigns", sa.Column("budget_fetched_at", sa.DateTime(), nullable=True))
    op.create_table(
        "wb_promotion_account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("balance", money, nullable=False),
        sa.Column("net", money, nullable=False),
        sa.Column("bonus", money, nullable=False),
        sa.Column("cashbacks", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_wb_promotion_account_snapshots_id", "wb_promotion_account_snapshots", ["id"])
    op.create_index("ix_wb_promotion_account_snapshots_fetched_at", "wb_promotion_account_snapshots", ["fetched_at"])
    op.create_table(
        "wb_promotion_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("payment_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount", money, nullable=False),
        sa.Column("payment_type", sa.String(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    for column in ("id", "source_hash", "payment_time", "payment_type"):
        op.create_index(f"ix_wb_promotion_payments_{column}", "wb_promotion_payments", [column], unique=column == "source_hash")


def downgrade() -> None:
    op.drop_table("wb_promotion_payments")
    op.drop_table("wb_promotion_account_snapshots")
    for column in ("budget_fetched_at", "budget_total", "budget_netting", "budget_cash"):
        op.drop_column("wb_advert_campaigns", column)
