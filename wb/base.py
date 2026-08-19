from abc import ABC, abstractmethod
from typing import Any

from wb.client import WBClient


class WBAPIBase(ABC):
    """Базовый класс для конкретных WB API-разделов."""

    def __init__(self, client: WBClient | None = None):
        self.client = client or WBClient()

    @abstractmethod
    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Получить список сущностей."""
        raise NotImplementedError
