from typing import Any

from app.db import SessionLocal
from app.models import WBSubject
from wb.categories import CategoriesAPI
from wb.repositories.category_repository import CategoryRepository


class CategoryService:
    """Сервис загрузки WB категорий и групп."""

    def __init__(self):
        self.api = CategoriesAPI()

    def sync_from_api(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.api.list(**kwargs)
        if not isinstance(payload, list):
            return []

        with SessionLocal() as session:
            repository = CategoryRepository(session)
            for item in payload:
                wb_id = item.get("subjectID") or item.get("id") or item.get("category_id") or item.get("wb_id")
                if wb_id is None:
                    continue
                wb_id = int(wb_id)

                existing = repository.get_by_wb_id(wb_id)
                if existing:
                    existing.name = item.get("subjectName") or item.get("name") or existing.name
                    existing.raw_data = item
                else:
                    repository.add(
                        WBSubject(
                            wb_id=wb_id,
                            name=item.get("subjectName") or item.get("name") or str(wb_id),
                            raw_data=item,
                        )
                    )

            session.commit()

        return payload
