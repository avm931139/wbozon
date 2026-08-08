from sqlalchemy import Column, Integer, String

from app.db import Base


class Example(Base):
    __tablename__ = "example"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
