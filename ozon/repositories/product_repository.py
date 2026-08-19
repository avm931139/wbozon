from sqlalchemy.orm import Session

from app.models import OzonProduct


class OzonProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, product_id: int) -> OzonProduct | None:
        return self.session.query(OzonProduct).filter_by(product_id=product_id).one_or_none()
