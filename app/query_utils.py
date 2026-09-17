from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeVar

from sqlalchemy import tuple_
from sqlalchemy.orm import Session


T = TypeVar("T")


def rows_by_keys(
    session: Session,
    model: type[T],
    key_column: Any,
    keys: Iterable[Any],
    *,
    batch_size: int = 1000,
) -> dict[Any, T]:
    """Load only rows addressed by the current input batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    unique_keys = list(dict.fromkeys(key for key in keys if key is not None))
    result: dict[Any, T] = {}
    for offset in range(0, len(unique_keys), batch_size):
        chunk = unique_keys[offset:offset + batch_size]
        for row in session.query(model).filter(key_column.in_(chunk)).all():
            result[getattr(row, key_column.key)] = row
    return result


def rows_by_composite_keys(
    session: Session,
    model: type[T],
    key_columns: tuple[Any, ...],
    keys: Iterable[tuple[Any, ...]],
    *,
    batch_size: int = 500,
) -> dict[tuple[Any, ...], T]:
    """Load rows addressed by composite keys without scanning the whole table."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    unique_keys = list(dict.fromkeys(keys))
    result: dict[tuple[Any, ...], T] = {}
    for offset in range(0, len(unique_keys), batch_size):
        chunk = unique_keys[offset:offset + batch_size]
        for row in session.query(model).filter(tuple_(*key_columns).in_(chunk)).all():
            result[tuple(getattr(row, column.key) for column in key_columns)] = row
    return result
