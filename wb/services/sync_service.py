from typing import Any

from wb.services.category_service import CategoryService
from wb.services.fbo_stock_service import FBOStockService
from wb.services.order_service import FBOOrderService, FBSOrderService
from wb.services.fbw_supply_service import FBWSupplyService
from wb.services.finance_service import FinanceService
from wb.services.customer_communication_service import CustomerCommunicationService
from wb.services.document_service import DocumentService
from wb.services.promotion_service import PromotionService
from wb.services.product_service import ProductService
from wb.services.stock_service import StockService
from wb.services.sales_service import SalesService
from wb.services.warehouse_service import WarehouseService


class WBSyncService:
    """Базовый сервис для загрузки данных из WB API."""

    def __init__(self):
        self.product_service = ProductService()
        self.warehouse_service = WarehouseService()
        self.stock_service = StockService()
        self.category_service = CategoryService()
        self.fbo_stock_service = FBOStockService()
        self.fbs_order_service = FBSOrderService()
        self.fbo_order_service = FBOOrderService()
        self.fbw_supply_service = FBWSupplyService()
        self.finance_service = FinanceService()
        self.customer_communication_service = CustomerCommunicationService()
        self.promotion_service = PromotionService()
        self.sales_service = SalesService()
        self.document_service = DocumentService()

        self.products_api = self.product_service.api
        self.warehouses_api = self.warehouse_service.api
        self.stocks_api = self.stock_service.api
        self.categories_api = self.category_service.api
        self.fbo_stocks_api = self.fbo_stock_service.api
        self.finances_api = self.finance_service.api
        self.customer_communications_api = self.customer_communication_service.api
        self.promotion_api = self.promotion_service.api
        self.documents_api = self.document_service.api

    def sync_products(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.product_service.sync_from_api(**kwargs)

    def sync_warehouses(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.warehouse_service.sync_from_api(**kwargs)

    def sync_stocks(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.stock_service.sync_from_api(**kwargs)

    def sync_fbs_warehouses(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.warehouse_service.sync_from_api(**kwargs)

    def sync_fbs_stocks(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.stock_service.sync_from_api(**kwargs)

    def sync_fbo_stocks(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.fbo_stock_service.sync_from_api(**kwargs)

    def sync_fbs_orders_max_history(self, **kwargs: Any) -> int:
        return self.fbs_order_service.sync_max_history(**kwargs)

    def sync_fbo_orders_max_history(self, **kwargs: Any) -> tuple[int, int]:
        return self.fbo_order_service.sync_max_history(**kwargs)

    def sync_sales_operations(self, **kwargs: Any) -> dict[str, int]:
        return self.sales_service.sync_all(**kwargs)

    def sales_summary(self, **kwargs: Any) -> dict[str, Any]:
        return self.sales_service.summary(**kwargs)

    def sync_fbw_supplies_max_history(self) -> dict[str, int]:
        return self.fbw_supply_service.sync_max_history()

    def sync_financial_sales_reports(self, **kwargs: Any) -> int:
        return self.finance_service.sync_sales_reports(**kwargs)

    def sync_financial_sales_details(self, **kwargs: Any) -> int:
        return self.finance_service.sync_sales_details(**kwargs)

    def sync_financial_acquiring_reports(self, **kwargs: Any) -> int:
        return self.finance_service.sync_acquiring_reports(**kwargs)

    def sync_financial_acquiring_details(self, **kwargs: Any) -> int:
        return self.finance_service.sync_acquiring_details(**kwargs)

    def sync_documents_and_accounting(self, **kwargs: Any) -> dict[str, Any]:
        return self.document_service.sync_all(**kwargs)

    def sync_missing_document_files(self, **kwargs: Any) -> dict[str, Any]:
        return self.document_service.sync_missing_files(**kwargs)

    def sync_customer_communications(self) -> dict[str, int]:
        return self.customer_communication_service.sync_all()

    def customer_communication_quality(self) -> dict[str, Any]:
        return self.customer_communication_service.quality_summary()

    def sync_advert_campaigns(self) -> int:
        return self.promotion_service.sync_campaigns()

    def sync_advert_expenses(self, **kwargs: Any) -> int:
        return self.promotion_service.sync_expenses(**kwargs)

    def sync_advert_stats(self, **kwargs: Any) -> int:
        return self.promotion_service.sync_stats(**kwargs)

    def sync_advertising(self, **kwargs: Any) -> dict[str, int]:
        return self.promotion_service.sync_all(**kwargs)

    def advert_efficiency(self, **kwargs: Any) -> dict[str, Any]:
        return self.promotion_service.efficiency_summary(**kwargs)

    def sync_categories(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.category_service.sync_from_api(**kwargs)
