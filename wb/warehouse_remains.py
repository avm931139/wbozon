from __future__ import annotations

import time
from typing import Any, Callable

from app.config import (
    WB_ANALYTICS_BASE_URL,
    WB_WAREHOUSE_REMAINS_POLL_ATTEMPTS,
    WB_WAREHOUSE_REMAINS_POLL_SECONDS,
)
from wb.client import WBClient
from wb.endpoints import WBEndpoints
from wb.exceptions import WBParseError


class WarehouseRemainsAPI:
    """Generate and download the full physical WB warehouse-remains report."""

    def __init__(
        self,
        client: WBClient | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or WBClient(base_url=WB_ANALYTICS_BASE_URL)
        self.sleeper = sleeper

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        created = self.client.get(
            WBEndpoints.WAREHOUSE_REMAINS_CREATE,
            params={
                "locale": kwargs.get("locale", "ru"),
                "groupByBrand": False,
                "groupBySubject": False,
                "groupBySa": True,
                "groupByNm": False,
                "groupByBarcode": False,
                "groupBySize": False,
                "filterPics": 0,
                "filterVolume": 0,
            },
        )
        data = created.get("data") if isinstance(created, dict) else None
        task_id = data.get("taskId") if isinstance(data, dict) else None
        if not task_id:
            raise WBParseError("WB warehouse remains response has no taskId")

        attempts = int(kwargs.get("attempts", WB_WAREHOUSE_REMAINS_POLL_ATTEMPTS))
        pause = float(kwargs.get("pause_seconds", WB_WAREHOUSE_REMAINS_POLL_SECONDS))
        for attempt in range(attempts):
            status_payload = self.client.get(
                WBEndpoints.WAREHOUSE_REMAINS_STATUS.format(task_id=task_id)
            )
            status_data = (
                status_payload.get("data") if isinstance(status_payload, dict) else None
            )
            status = str(
                status_data.get("status") if isinstance(status_data, dict) else ""
            ).lower()
            if status == "done":
                break
            if status in {"purged", "canceled"}:
                raise WBParseError(
                    f"WB warehouse remains task {task_id} ended with status {status}"
                )
            if attempt == attempts - 1:
                raise WBParseError(
                    f"WB warehouse remains task {task_id} was not ready after {attempts} polls"
                )
            self.sleeper(pause)

        report = self.client.get(
            WBEndpoints.WAREHOUSE_REMAINS_DOWNLOAD.format(task_id=task_id)
        )
        if report is None:
            return []
        if not isinstance(report, list) or not all(isinstance(row, dict) for row in report):
            raise WBParseError("WB warehouse remains download is not a row list")
        return report
