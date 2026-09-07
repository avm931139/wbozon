"""sanitize Ozon finance posting identifiers

Revision ID: 20260907_ozon_accrual_fix
Revises: 20260907_ozon_accruals
"""

from alembic import op


revision = "20260907_ozon_accrual_fix"
down_revision = "20260907_ozon_accruals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE ozon_finance_accruals
        SET posting_number = NULL
        WHERE posting_number IS NOT NULL
          AND posting_number !~ '^[0-9]{1,32}-[0-9]{1,32}-[0-9]{1,32}$'
    """)


def downgrade() -> None:
    pass
