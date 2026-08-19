from typing import Any

from app.db import SessionLocal
from app.models import WBFBSWarehouse
from wb.warehouses import WarehousesAPI
from wb.repositories.warehouse_repository import WarehouseRepository


class WarehouseService:
    """Сервис загрузки WB складов."""

    def __init__(self):
        self.api = WarehousesAPI()

    def sync_from_api(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.api.list(**kwargs)
        if not isinstance(payload, list):
            return []

        with SessionLocal() as session:
            repository = WarehouseRepository(session)
            for item in payload:
                wb_id = item.get("id") or item.get("warehouseId") or item.get("wb_id")
                if wb_id is None:
                    continue
                wb_id = int(wb_id)

                existing = repository.get_by_wb_id(wb_id)
                if existing:
                    existing.name = item.get("name") or existing.name
                    existing.office_id = item.get("officeId")
                    existing.cargo_type = item.get("cargoType")
                    existing.delivery_type = item.get("deliveryType")
                    existing.is_deleting = item.get("isDeleting")
                    existing.is_processing = item.get("isProcessing")
                    existing.raw_data = item
                else:
                    repository.add(
                        WBFBSWarehouse(
                            wb_id=wb_id,
                            name=item.get("name"),
                            office_id=item.get("officeId"),
                            cargo_type=item.get("cargoType"),
                            delivery_type=item.get("deliveryType"),
                            is_deleting=item.get("isDeleting"),
                            is_processing=item.get("isProcessing"),
                            raw_data=item,
                        )
                    )

            session.commit()

        return payload
