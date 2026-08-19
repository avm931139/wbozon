"""add signed acquiring amounts

Revision ID: 20260809_add_signed_acquiring
Revises: 20260809_add_financial_reports
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_add_signed_acquiring"
down_revision = "20260809_add_financial_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    money = sa.Numeric(20, 6)
    op.add_column("wb_financial_acquiring_rows", sa.Column("operation_sign", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("wb_financial_acquiring_rows", sa.Column("signed_retail_amount", money, nullable=False, server_default="0"))
    op.add_column("wb_financial_acquiring_rows", sa.Column("signed_acquiring_fee", money, nullable=False, server_default="0"))
    op.add_column("wb_financial_acquiring_rows", sa.Column("signed_acquiring_fee_vat", money, nullable=False, server_default="0"))
    op.execute(sa.text("""
        UPDATE wb_financial_acquiring_rows
        SET operation_sign = CASE WHEN lower(document_type) = 'возврат' THEN -1 ELSE 1 END,
            signed_retail_amount = retail_amount * CASE WHEN lower(document_type) = 'возврат' THEN -1 ELSE 1 END,
            signed_acquiring_fee = acquiring_fee * CASE WHEN lower(document_type) = 'возврат' THEN -1 ELSE 1 END,
            signed_acquiring_fee_vat = acquiring_fee_vat * CASE WHEN lower(document_type) = 'возврат' THEN -1 ELSE 1 END
    """))
    for column in ("operation_sign", "signed_retail_amount", "signed_acquiring_fee", "signed_acquiring_fee_vat"):
        op.alter_column("wb_financial_acquiring_rows", column, server_default=None)


def downgrade() -> None:
    for column in ("signed_acquiring_fee_vat", "signed_acquiring_fee", "signed_retail_amount", "operation_sign"):
        op.drop_column("wb_financial_acquiring_rows", column)
