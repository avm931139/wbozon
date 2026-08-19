from sqlalchemy.orm import Session

from app.models import OzonPosting


class OzonPostingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, posting_number: str, scheme: str) -> OzonPosting | None:
        return self.session.query(OzonPosting).filter_by(posting_number=posting_number, scheme=scheme).one_or_none()
