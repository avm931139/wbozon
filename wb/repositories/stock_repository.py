from sqlalchemy.orm import Session

from app.models import WBFBSStock
from wb.repositories.base_repository import BaseRepository


class StockRepository(BaseRepository[WBFBSStock]):
    def __init__(self, session: Session):
        super().__init__(session, WBFBSStock)

    def get_by_sku_and_warehouse(self, sku: str, warehouse_id: int) -> WBFBSStock | None:
        return self.get_first_by(sku=sku, warehouse_id=warehouse_id)
