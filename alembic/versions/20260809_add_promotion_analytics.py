"""add promotion costs and analytics"""
from alembic import op
import sqlalchemy as sa

revision = "20260809_promotion_analytics"
down_revision = "20260809_customer_communications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    money = sa.Numeric(20, 6); ratio = sa.Numeric(12, 6)
    op.create_table("wb_advert_campaigns", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("advert_wb_id",sa.BigInteger(),nullable=False,unique=True),sa.Column("name",sa.String()),sa.Column("advert_type",sa.Integer()),sa.Column("status",sa.Integer()),sa.Column("change_time",sa.DateTime(timezone=True)),sa.Column("raw_data",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),comment="Рекламные кампании WB Продвижение и их последнее известное состояние.")
    for c in ("id","advert_wb_id","advert_type","status","change_time"): op.create_index(f"ix_wb_advert_campaigns_{c}","wb_advert_campaigns",[c],unique=c=="advert_wb_id")
    op.create_table("wb_advert_expenses",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("campaign_id",sa.Integer(),sa.ForeignKey("wb_advert_campaigns.id")),sa.Column("upd_num",sa.BigInteger()),sa.Column("source_hash",sa.String(64),nullable=False),sa.Column("expense_time",sa.DateTime(timezone=True)),sa.Column("amount",money,nullable=False),sa.Column("currency",sa.String(),nullable=False),sa.Column("payment_type",sa.String()),sa.Column("advert_type",sa.Integer()),sa.Column("advert_status",sa.Integer()),sa.Column("campaign_name",sa.String()),sa.Column("raw_data",sa.JSON(),nullable=False),sa.Column("fetched_at",sa.DateTime(),nullable=False),sa.UniqueConstraint("source_hash",name="uq_wb_advert_expense_source_hash"),comment="Фактические списания средств на рекламные кампании из истории затрат WB.")
    for c in ("id","campaign_id","upd_num","source_hash","expense_time","payment_type"): op.create_index(f"ix_wb_advert_expenses_{c}","wb_advert_expenses",[c])
    metric_columns = [sa.Column(c,sa.BigInteger(),nullable=False) for c in ("views","clicks","atbs","orders","canceled","shks")]
    op.create_table("wb_advert_daily_stats",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("campaign_id",sa.Integer(),sa.ForeignKey("wb_advert_campaigns.id",ondelete="CASCADE"),nullable=False),sa.Column("stat_date",sa.DateTime(timezone=True),nullable=False),*metric_columns,sa.Column("spend",money,nullable=False),sa.Column("order_sum",money,nullable=False),sa.Column("ctr",ratio,nullable=False),sa.Column("cpc",money,nullable=False),sa.Column("cr",ratio,nullable=False),sa.Column("raw_data",sa.JSON(),nullable=False),sa.Column("fetched_at",sa.DateTime(),nullable=False),sa.UniqueConstraint("campaign_id","stat_date",name="uq_wb_advert_daily_stat"),comment="Контрольные дневные показатели рекламной кампании WB.")
    for c in ("id","campaign_id","stat_date"): op.create_index(f"ix_wb_advert_daily_stats_{c}","wb_advert_daily_stats",[c])
    product_metrics = [sa.Column(c,sa.BigInteger(),nullable=False) for c in ("views","clicks","atbs","orders","canceled","shks")]
    op.create_table("wb_advert_product_daily_stats",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("daily_stat_id",sa.Integer(),sa.ForeignKey("wb_advert_daily_stats.id",ondelete="CASCADE"),nullable=False),sa.Column("product_id",sa.Integer(),sa.ForeignKey("wb_products.id")),sa.Column("nm_id",sa.BigInteger(),nullable=False),sa.Column("app_type",sa.Integer(),nullable=False),sa.Column("product_name",sa.String()),*product_metrics,sa.Column("spend",money,nullable=False),sa.Column("order_sum",money,nullable=False),sa.Column("ctr",ratio,nullable=False),sa.Column("cpc",money,nullable=False),sa.Column("cr",ratio,nullable=False),sa.Column("raw_data",sa.JSON(),nullable=False),sa.UniqueConstraint("daily_stat_id","app_type","nm_id",name="uq_wb_advert_product_daily_stat"),comment="Дневная рекламная статистика WB в разрезе площадки и товара nmId.")
    for c in ("id","daily_stat_id","product_id","nm_id","app_type"): op.create_index(f"ix_wb_advert_product_daily_stats_{c}","wb_advert_product_daily_stats",[c])


def downgrade() -> None:
    for table in ("wb_advert_product_daily_stats","wb_advert_daily_stats","wb_advert_expenses","wb_advert_campaigns"): op.drop_table(table)
