from app.config import OZON_PERFORMANCE_CLIENT_ID, OZON_PERFORMANCE_CLIENT_SECRET
from ozon.services.order_service import OzonOrderService
from ozon.services.product_service import OzonProductService
from ozon.services.stock_service import OzonStockService
from ozon.services.overview_service import OzonOverviewService


class OzonSyncService:
    TASK_NAMES = (
        "products",
        "orders",
        "supplies",
        "communications",
        "daily_sales",
        "finances",
        "documents",
        "ads",
    )

    def __init__(self) -> None:
        self.product_service = OzonProductService()
        self.stock_service = OzonStockService()
        self.order_service = OzonOrderService()
        self.overview_service = OzonOverviewService()

    def sync_products(self):
        return self.product_service.sync_from_api()

    def sync_stocks(self):
        return self.stock_service.sync_from_api()

    def sync_orders(self):
        return self.order_service.sync_recent()

    def sync_supplies(self):
        return self.overview_service.sync_supplies()

    def sync_communications(self):
        return self.overview_service.sync_communications()

    def sync_daily_sales(self):
        return self.overview_service.sync_daily_sales()

    def sync_finances(self):
        return self.overview_service.sync_finances()

    def sync_documents(self):
        from ozon.services.accounting_service import OzonAccountingService
        return OzonAccountingService().sync_all()

    def sync_ads(self):
        if not OZON_PERFORMANCE_CLIENT_ID or not OZON_PERFORMANCE_CLIENT_SECRET:
            return {"skipped": True, "reason": "Performance API credentials are not configured"}
        from ozon.performance.service import OzonPerformanceService
        return OzonPerformanceService().sync_all()

    @classmethod
    def task_names(cls) -> tuple[str, ...]:
        return cls.TASK_NAMES

    def run_task(self, task: str):
        callbacks = {
            "products": self.sync_products,
            "orders": self.sync_orders,
            "supplies": self.sync_supplies,
            "communications": self.sync_communications,
            "daily_sales": self.sync_daily_sales,
            "finances": self.sync_finances,
            "documents": self.sync_documents,
            "ads": self.sync_ads,
        }
        try:
            callback = callbacks[task]
        except KeyError as exc:
            raise ValueError(f"unknown Ozon task: {task}") from exc
        return callback()
