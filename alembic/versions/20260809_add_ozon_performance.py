"""add Ozon Performance advertising tables"""
from alembic import op
import sqlalchemy as sa
revision="20260809_ozon_ads"; down_revision="20260809_ozon_overview"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("ozon_ad_campaigns",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("campaign_id",sa.BigInteger(),nullable=False,unique=True),sa.Column("title",sa.String()),sa.Column("state",sa.String()),sa.Column("campaign_type",sa.String()),sa.Column("payment_type",sa.String()),sa.Column("budget",sa.Numeric(20,6),nullable=False,server_default="0"),sa.Column("daily_budget",sa.Numeric(20,6),nullable=False,server_default="0"),sa.Column("from_date",sa.Date()),sa.Column("to_date",sa.Date()),sa.Column("raw_data",sa.JSON(),nullable=False),sa.Column("fetched_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("ozon_ad_daily_stats",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("stat_date",sa.Date(),nullable=False),sa.Column("campaign_id",sa.BigInteger(),nullable=False),sa.Column("sku",sa.BigInteger(),nullable=False,server_default="0"),sa.Column("views",sa.BigInteger(),nullable=False,server_default="0"),sa.Column("clicks",sa.BigInteger(),nullable=False,server_default="0"),sa.Column("orders",sa.Integer(),nullable=False,server_default="0"),sa.Column("orders_money",sa.Numeric(20,6),nullable=False,server_default="0"),sa.Column("spend",sa.Numeric(20,6),nullable=False,server_default="0"),sa.Column("raw_data",sa.JSON(),nullable=False),sa.Column("fetched_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("stat_date","campaign_id","sku",name="uq_ozon_ad_daily_stat"))
    for table,cols in {"ozon_ad_campaigns":["campaign_id","state","campaign_type"],"ozon_ad_daily_stats":["stat_date","campaign_id","sku"]}.items():
        for col in cols: op.create_index(f"ix_{table}_{col}",table,[col])
def downgrade():
    op.drop_table("ozon_ad_daily_stats"); op.drop_table("ozon_ad_campaigns")
