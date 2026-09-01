"""add Ozon FBO sent-versus-accepted reconciliation

Revision ID: 20260901_ozon_fbo_recon
Revises: 20260831_ozon_accounting
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_ozon_fbo_recon"
down_revision = "20260831_ozon_accounting"
branch_labels = None
depends_on = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "ozon_fbo_supply_declared_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supply_order_id", sa.BigInteger(), nullable=False),
        sa.Column("supply_id", sa.BigInteger(), nullable=False),
        sa.Column("bundle_id", sa.String(), nullable=False),
        sa.Column("supply_state", sa.String(), nullable=True),
        sa.Column("storage_warehouse_id", sa.BigInteger(), nullable=True),
        sa.Column("storage_warehouse_name", sa.String(), nullable=True),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("declared_quantity", sa.Integer(), nullable=False),
        sa.Column("pack_quantity", sa.Integer(), nullable=True),
        sa.Column("shipment_type", sa.String(), nullable=True),
        sa.Column("placement_zone", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("supply_id", "sku", name="uq_ozon_fbo_declared_supply_sku"),
    )
    _indexes(
        "ozon_fbo_supply_declared_items",
        (
            "id", "supply_order_id", "supply_id", "bundle_id", "supply_state",
            "storage_warehouse_id", "sku", "product_id", "offer_id", "fetched_at",
        ),
    )

    op.create_table(
        "ozon_fbo_supply_acts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supply_order_id", sa.BigInteger(), nullable=False),
        sa.Column("supply_id", sa.BigInteger(), nullable=False),
        sa.Column("act_id", sa.BigInteger(), nullable=False),
        sa.Column("act_number", sa.String(), nullable=True),
        sa.Column("act_type", sa.String(), nullable=False),
        sa.Column("act_state", sa.String(), nullable=True),
        sa.Column("act_created_date", sa.Date(), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_agreement_completed", sa.Boolean(), nullable=False),
        sa.Column("declared_quantity", sa.Integer(), nullable=False),
        sa.Column("fact_quantity", sa.Integer(), nullable=False),
        sa.Column("approved_quantity", sa.Integer(), nullable=False),
        sa.Column("sku_quantity", sa.Integer(), nullable=False),
        sa.Column("unidentified_quantity", sa.Integer(), nullable=False),
        sa.Column("declared_amount", sa.JSON(), nullable=True),
        sa.Column("fact_amount", sa.JSON(), nullable=True),
        sa.Column("approved_amount", sa.JSON(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("act_id", name="uq_ozon_fbo_supply_acts_act_id"),
    )
    _indexes(
        "ozon_fbo_supply_acts",
        (
            "id", "supply_order_id", "supply_id", "act_id", "act_number",
            "act_type", "act_state", "act_created_date", "is_agreement_completed",
            "fetched_at",
        ),
    )

    op.create_table(
        "ozon_fbo_supply_act_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supply_order_id", sa.BigInteger(), nullable=False),
        sa.Column("supply_id", sa.BigInteger(), nullable=False),
        sa.Column("act_id", sa.BigInteger(), nullable=False),
        sa.Column("act_type", sa.String(), nullable=False),
        sa.Column("sku", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("declared_quantity", sa.Integer(), nullable=False),
        sa.Column("fact_quantity", sa.Integer(), nullable=False),
        sa.Column("approved_quantity", sa.Integer(), nullable=False),
        sa.Column("price_without_vat", sa.JSON(), nullable=True),
        sa.Column("fact_amount", sa.JSON(), nullable=True),
        sa.Column("approved_amount", sa.JSON(), nullable=True),
        sa.Column("defect_reasons", sa.JSON(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("act_id", "sku", name="uq_ozon_fbo_act_item_act_sku"),
    )
    _indexes(
        "ozon_fbo_supply_act_items",
        (
            "id", "supply_order_id", "supply_id", "act_id", "act_type", "sku",
            "offer_id", "fetched_at",
        ),
    )

    op.execute("""
        CREATE VIEW ozon_fbo_supply_reconciliation AS
        WITH accepted AS (
            SELECT
                items.supply_order_id,
                items.supply_id,
                items.sku,
                MAX(items.offer_id) AS offer_id,
                BOOL_OR(COALESCE(acts.is_agreement_completed, false)) AS is_acceptance_completed,
                SUM(CASE WHEN items.act_type = 'ACCEPTANCE' THEN items.fact_quantity ELSE 0 END) AS accepted_quantity,
                SUM(CASE WHEN items.act_type = 'ACCEPTANCE' THEN items.approved_quantity ELSE 0 END) AS approved_quantity,
                SUM(CASE WHEN items.act_type = 'DEFECT' THEN items.fact_quantity ELSE 0 END) AS defect_fact_quantity,
                SUM(CASE WHEN items.act_type = 'SURPLUS' THEN items.fact_quantity ELSE 0 END) AS surplus_fact_quantity,
                SUM(CASE WHEN items.act_type = 'SHORTCOMING' THEN items.fact_quantity ELSE 0 END) AS shortcoming_fact_quantity,
                MAX(items.fetched_at) AS act_fetched_at
            FROM ozon_fbo_supply_act_items AS items
            LEFT JOIN ozon_fbo_supply_acts AS acts ON acts.act_id = items.act_id
            GROUP BY items.supply_order_id, items.supply_id, items.sku
        )
        SELECT
            COALESCE(declared.supply_order_id, accepted.supply_order_id) AS supply_order_id,
            COALESCE(declared.supply_id, accepted.supply_id) AS supply_id,
            COALESCE(declared.sku, accepted.sku) AS sku,
            COALESCE(declared.offer_id, accepted.offer_id) AS offer_id,
            declared.bundle_id,
            declared.supply_state,
            declared.storage_warehouse_id,
            declared.storage_warehouse_name,
            COALESCE(declared.declared_quantity, 0) AS sent_quantity,
            COALESCE(accepted.accepted_quantity, 0) AS accepted_quantity,
            COALESCE(accepted.approved_quantity, 0) AS approved_quantity,
            COALESCE(accepted.is_acceptance_completed, false) AS is_acceptance_completed,
            COALESCE(accepted.accepted_quantity, 0) - COALESCE(declared.declared_quantity, 0)
                AS quantity_difference,
            COALESCE(accepted.defect_fact_quantity, 0) AS defect_fact_quantity,
            COALESCE(accepted.surplus_fact_quantity, 0) AS surplus_fact_quantity,
            COALESCE(accepted.shortcoming_fact_quantity, 0) AS shortcoming_fact_quantity,
            declared.fetched_at AS bundle_fetched_at,
            accepted.act_fetched_at
        FROM ozon_fbo_supply_declared_items AS declared
        FULL OUTER JOIN accepted
            ON accepted.supply_order_id = declared.supply_order_id
           AND accepted.supply_id = declared.supply_id
           AND accepted.sku = declared.sku
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS ozon_fbo_supply_reconciliation")
    op.drop_table("ozon_fbo_supply_act_items")
    op.drop_table("ozon_fbo_supply_acts")
    op.drop_table("ozon_fbo_supply_declared_items")
