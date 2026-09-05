from __future__ import annotations

from yandex_market.services.catalog_service import YandexMarketCatalogService
from yandex_market.services.identity_service import YandexMarketIdentityService
from yandex_market.services.order_service import YandexMarketOrderService


class YandexMarketSyncService:
    TASK_NAMES = ("identity", "catalog", "orders")

    def __init__(self) -> None:
        self.identity_service = YandexMarketIdentityService()
        self.catalog_service = YandexMarketCatalogService()
        self.order_service = YandexMarketOrderService()

    @classmethod
    def task_names(cls) -> tuple[str, ...]:
        return cls.TASK_NAMES

    def run_task(self, task: str):
        callbacks = {
            "identity": self.identity_service.sync,
            "catalog": self.catalog_service.sync,
            "orders": self.order_service.sync,
        }
        try:
            return callbacks[task]()
        except KeyError as exc:
            raise ValueError(f"unknown Yandex Market task: {task}") from exc
