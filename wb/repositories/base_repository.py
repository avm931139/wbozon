from typing import Any, Generic, TypeVar

from sqlalchemy.orm import Session


ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Базовые операции SQLAlchemy для WB-сущностей."""

    def __init__(self, session: Session, model: type[ModelT]):
        self.session = session
        self.model = model

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    def get_first_by(self, **filters: Any) -> ModelT | None:
        return self.session.query(self.model).filter_by(**filters).first()
