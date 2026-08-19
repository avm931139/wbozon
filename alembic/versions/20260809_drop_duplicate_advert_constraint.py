"""Drop duplicate uniqueness constraint for WB advertising campaign ID.

Revision ID: 20260809_advert_unique_cleanup
Revises: 20260809_promotion_analytics
Create Date: 2026-08-09
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260809_advert_unique_cleanup"
down_revision: str | None = "20260809_promotion_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "wb_advert_campaigns_advert_wb_id_key",
        "wb_advert_campaigns",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "wb_advert_campaigns_advert_wb_id_key",
        "wb_advert_campaigns",
        ["advert_wb_id"],
    )
