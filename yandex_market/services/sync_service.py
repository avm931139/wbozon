from __future__ import annotations

from yandex_market.services.catalog_service import YandexMarketCatalogService
from yandex_market.services.advertising_service import YandexMarketAdvertisingService
from yandex_market.services.identity_service import YandexMarketIdentityService
from yandex_market.services.finance_service import YandexMarketFinanceService
from yandex_market.services.order_service import YandexMarketOrderService
from yandex_market.services.sales_analytics_service import YandexMarketSalesAnalyticsService


class YandexMarketSyncService:
    TASK_NAMES = ("identity", "catalog", "orders", "advertising", "finances", "analytics")

    def __init__(self) -> None:
        self.identity_service = YandexMarketIdentityService()
        self.catalog_service = YandexMarketCatalogService()
        self.order_service = YandexMarketOrderService()
        self.advertising_service = YandexMarketAdvertisingService()
        self.finance_service = YandexMarketFinanceService()
        self.sales_analytics_service = YandexMarketSalesAnalyticsService()

    @classmethod
    def task_names(cls) -> tuple[str, ...]:
        return cls.TASK_NAMES

    def run_task(self, task: str):
        callbacks = {
            "identity": self.identity_service.sync,
            "catalog": self.catalog_service.sync,
            "orders": self.order_service.sync,
            "advertising": self.advertising_service.sync,
            "finances": self.finance_service.sync,
            "analytics": self.sales_analytics_service.sync,
        }
        try:
            return callbacks[task]()
        except KeyError as exc:
            raise ValueError(f"unknown Yandex Market task: {task}") from exc
