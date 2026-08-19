from sqlalchemy.orm import Session

from app.models import WBSubject
from wb.repositories.base_repository import BaseRepository


class CategoryRepository(BaseRepository[WBSubject]):
    def __init__(self, session: Session):
        super().__init__(session, WBSubject)

    def get_by_wb_id(self, wb_id: int) -> WBSubject | None:
        return self.get_first_by(wb_id=wb_id)
