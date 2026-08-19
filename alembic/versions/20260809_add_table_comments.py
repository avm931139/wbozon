"""add comments to application tables

Revision ID: 20260809_add_table_comments
Revises: 20260809_add_signed_acquiring
"""

from alembic import op

revision = "20260809_add_table_comments"
down_revision = "20260809_add_signed_acquiring"
branch_labels = None
depends_on = None


TABLE_COMMENTS = {
    "example": "Техническая тестовая таблица для проверки подключения к БД.",
    "wb_subjects": "Справочник предметов (категорий товаров) Wildberries.",
    "wb_products": "Основные карточки товаров Wildberries.",
    "wb_product_photos": "Фотографии карточек товаров Wildberries в порядке отображения.",
    "wb_product_dimensions": "Габариты и масса упаковки товара Wildberries.",
    "wb_characteristics": "Справочник характеристик товаров Wildberries.",
    "wb_product_characteristics": "Значения характеристик, назначенные карточкам товаров Wildberries.",
    "wb_product_sizes": "Размеры и chrtId товарных карточек Wildberries.",
    "wb_size_barcodes": "Баркоды, связанные с размерами товаров Wildberries.",
    "wb_fbs_warehouses": "Склады продавца Wildberries для схемы FBS.",
    "wb_fbs_stocks": "Текущие остатки товаров на складах продавца по схеме FBS.",
    "wb_fbo_warehouses": "Склады Wildberries для схемы FBO с региональной принадлежностью.",
    "wb_fbo_stocks": "Остатки и товары в пути на складах Wildberries по схеме FBO.",
    "wb_fbs_orders": "Заказы Wildberries, обрабатываемые продавцом по схеме FBS.",
    "wb_fbo_orders": "История заказов Wildberries, исполненных со складов WB по схеме FBO.",
    "wb_fbw_warehouses": "Справочник складов Wildberries, доступных для поставок FBW.",
    "wb_fbw_supplies": "Поставки и предварительные поставки продавца на склады Wildberries (FBW).",
    "wb_fbw_supply_goods": "Товарные позиции и количества внутри поставок FBW.",
    "wb_fbw_supply_packages": "Короба, палеты и другие упаковки поставок FBW.",
    "wb_fbw_supply_package_goods": "Распределение товарных баркодов по упаковкам поставки FBW.",
    "wb_fbw_supply_snapshots": "История состояний и количественных показателей поставок FBW.",
    "wb_financial_sales_reports": "Сводные финансовые отчёты Wildberries о продажах и реализации.",
    "wb_financial_sales_rows": "Детализированные финансовые операции отчётов реализации Wildberries.",
    "wb_financial_acquiring_reports": "Сводные отчёты Wildberries об издержках на приём платежей.",
    "wb_financial_acquiring_rows": "Детализация эквайринга Wildberries с исходными и знаковыми суммами операций.",
}


def upgrade() -> None:
    for table, comment in TABLE_COMMENTS.items():
        op.create_table_comment(table, comment, existing_comment=None)


def downgrade() -> None:
    for table, comment in TABLE_COMMENTS.items():
        op.drop_table_comment(table, existing_comment=comment)
