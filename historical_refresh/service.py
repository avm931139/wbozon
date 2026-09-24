from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Callable

from analytics_facts.service import FinancialSalesFactService, MARKETPLACES
from app.config import (
    HISTORY_REFRESH_LOOKBACK_DAYS,
    OZON_HISTORY_FROM,
    OZON_PERFORMANCE_CLIENT_ID,
    OZON_PERFORMANCE_CLIENT_SECRET,
    WB_SYNC_HISTORY_START,
    YANDEX_MARKET_HISTORY_FROM,
)
from ozon.business_time import ozon_today
from ozon.performance.service import OzonPerformanceService
from ozon.services.finance_service import OzonFinanceSyncService
from wb.services.finance_service import FinanceService as WBFinanceService
from wb.services.promotion_service import PromotionService as WBPromotionService
from yandex_market.services.advertising_service import YandexMarketAdvertisingService
from yandex_market.services.finance_service import YandexMarketFinanceService


logger = logging.getLogger(__name__)


class HistoricalRefreshService:
    """Reload mutable marketplace history and then rebuild normalized facts."""

    def __init__(
        self,
        *,
        today: Callable[[], date] = ozon_today,
        lookback_days: int = HISTORY_REFRESH_LOOKBACK_DAYS,
    ) -> None:
        if lookback_days < 1:
            raise ValueError("HISTORY_REFRESH_LOOKBACK_DAYS must be positive")
        self.today = today
        self.lookback_days = lookback_days

    def run(
        self,
        *,
        marketplace: str = "all",
        mode: str = "rolling",
        date_from: date | None = None,
        date_to: date | None = None,
        include_advertising: bool = True,
    ) -> dict[str, Any]:
        if marketplace != "all" and marketplace not in MARKETPLACES:
            raise ValueError(f"unsupported marketplace: {marketplace}")
        if mode not in {"full", "rolling"}:
            raise ValueError(f"unsupported history refresh mode: {mode}")
        finish = min(date_to or self.today(), self.today())
        selected = MARKETPLACES if marketplace == "all" else (marketplace,)
        results: dict[str, Any] = {}
        for name in selected:
            start = self._start(name, mode, finish, date_from)
            results[name] = self._run_marketplace(
                name, start, finish, include_advertising=include_advertising
            )
        status = "partial" if any(
            item["status"] != "completed" for item in results.values()
        ) else "completed"
        return {
            "status": status,
            "mode": mode,
            "date_to": finish.isoformat(),
            "marketplaces": results,
        }

    def _start(
        self,
        marketplace: str,
        mode: str,
        finish: date,
        requested: date | None,
    ) -> date:
        configured = date.fromisoformat({
            "wb": WB_SYNC_HISTORY_START,
            "ozon": OZON_HISTORY_FROM,
            "yandex_market": YANDEX_MARKET_HISTORY_FROM,
        }[marketplace])
        automatic = (
            configured
            if mode == "full"
            else max(configured, finish - timedelta(days=self.lookback_days - 1))
        )
        start = max(configured, requested or automatic)
        if start > finish:
            raise ValueError(f"{marketplace} history date_from must not exceed date_to")
        return start

    def _run_marketplace(
        self,
        marketplace: str,
        start: date,
        finish: date,
        *,
        include_advertising: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "completed",
            "date_from": start.isoformat(),
            "date_to": finish.isoformat(),
        }
        errors: list[str] = []
        steps = self._raw_steps(
            marketplace, start, finish, include_advertising=include_advertising
        )
        for name, callback in steps:
            try:
                result[name] = callback()
            except Exception as exc:
                logger.exception("%s historical %s refresh failed", marketplace, name)
                message = f"{name}: {type(exc).__name__}: {exc}"
                result[f"{name}_error"] = message
                errors.append(message)
        try:
            result["analytics"] = FinancialSalesFactService(marketplace).run()
        except Exception as exc:
            logger.exception("%s analytical layer rebuild failed", marketplace)
            message = f"analytics: {type(exc).__name__}: {exc}"
            result["analytics_error"] = message
            errors.append(message)
        if errors:
            result["status"] = "partial"
            result["errors"] = errors
        return result

    @staticmethod
    def _raw_steps(
        marketplace: str,
        start: date,
        finish: date,
        *,
        include_advertising: bool,
    ) -> list[tuple[str, Callable[[], Any]]]:
        if marketplace == "wb":
            finance = WBFinanceService()
            steps: list[tuple[str, Callable[[], Any]]] = [
                ("finance", lambda: finance.sync_history(start, finish)),
            ]
            if include_advertising:
                promotion = WBPromotionService()
                steps.append(
                    ("advertising", lambda: promotion.sync_all(start, finish))
                )
            return steps
        if marketplace == "ozon":
            finance = OzonFinanceSyncService(history_from=start)
            steps = [
                ("finance", lambda: finance.sync_history(date_from=start, date_to=finish)),
            ]
            if (
                include_advertising
                and OZON_PERFORMANCE_CLIENT_ID
                and OZON_PERFORMANCE_CLIENT_SECRET
            ):
                advertising = OzonPerformanceService()
                steps.append((
                    "advertising",
                    lambda: advertising.sync_history(date_from=start, date_to=finish),
                ))
            elif include_advertising:
                steps.append(("advertising", lambda: {
                    "skipped": True,
                    "reason": "Ozon Performance API credentials are not configured",
                }))
            return steps
        finance = YandexMarketFinanceService()
        steps = [
            ("finance", lambda: finance.sync_history(date_from=start, date_to=finish)),
        ]
        if include_advertising:
            advertising = YandexMarketAdvertisingService()
            steps.append((
                "advertising",
                lambda: advertising.sync_history(date_from=start, date_to=finish),
            ))
        return steps
