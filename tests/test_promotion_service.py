from datetime import date

import pytest

from wb.services.promotion_service import _date_chunks, _expense_hash


def test_date_chunks_are_inclusive_and_respect_31_day_limit():
    chunks = list(_date_chunks(date(2026, 1, 1), date(2026, 3, 5)))

    assert chunks == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 3, 3)),
        (date(2026, 3, 4), date(2026, 3, 5)),
    ]


def test_date_chunks_reject_reverse_period():
    with pytest.raises(ValueError, match="date_from"):
        list(_date_chunks(date(2026, 2, 1), date(2026, 1, 1)))


def test_expense_identity_ignores_mutable_campaign_metadata():
    original = {
        "updNum": 42,
        "advertId": 100,
        "updTime": "2026-08-09T10:00:00Z",
        "updSum": 120.5,
        "paymentType": "Баланс",
        "campName": "Old name",
        "advertStatus": 7,
    }
    changed = {**original, "campName": "New name", "advertStatus": 11}

    assert _expense_hash(original) == _expense_hash(changed)


def test_expense_identity_changes_for_another_operation():
    first = {"updNum": 1, "advertId": 100, "updTime": "2026-08-09", "updSum": 10}
    second = {**first, "updNum": 2}

    assert _expense_hash(first) != _expense_hash(second)
