from sqlalchemy.orm import Session

from app.models import OzonStock


class OzonStockRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, product_id: int, stock_type: str) -> OzonStock | None:
        return self.session.query(OzonStock).filter_by(product_id=product_id, stock_type=stock_type).one_or_none()
