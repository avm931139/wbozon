from sqlalchemy.orm import Session

from app.models import WBProduct
from wb.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository[WBProduct]):
    def __init__(self, session: Session):
        super().__init__(session, WBProduct)

    def get_by_nm_id(self, nm_id: int) -> WBProduct | None:
        return self.get_first_by(nm_id=nm_id)
