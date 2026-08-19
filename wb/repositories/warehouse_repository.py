from sqlalchemy.orm import Session

from app.models import WBFBSWarehouse
from wb.repositories.base_repository import BaseRepository


class WarehouseRepository(BaseRepository[WBFBSWarehouse]):
    def __init__(self, session: Session):
        super().__init__(session, WBFBSWarehouse)

    def get_by_wb_id(self, wb_id: int) -> WBFBSWarehouse | None:
        return self.get_first_by(wb_id=wb_id)
