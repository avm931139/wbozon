"""Split normalized advertising spend into direct and allocated components.

Revision ID: 20260924_ad_spend_parts
Revises: 20260924_advertising_facts
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_ad_spend_parts"
down_revision = "20260924_advertising_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fact_advertising_daily",
        sa.Column("direct_spend_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "fact_advertising_daily",
        sa.Column("allocated_spend_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("fact_advertising_daily", "allocated_spend_kopecks")
    op.drop_column("fact_advertising_daily", "direct_spend_kopecks")
