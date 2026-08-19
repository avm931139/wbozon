from wb.sync_logging import build_error_event, summarize_result, sync_context


def _raise_test_error():
    raise ValueError("bad row")


def test_error_event_contains_origin_and_cycle_context():
    with sync_context("cycle-1", "products"):
        try:
            _raise_test_error()
        except ValueError as exc:
            event = build_error_event(exc, phase="write", details={"nm_id": 42})

    assert event["cycle_id"] == "cycle-1"
    assert event["task"] == "products"
    assert event["phase"] == "write"
    assert event["exception_type"] == "ValueError"
    assert event["file"].endswith("test_wb_sync_logging.py")
    assert event["function"] == "_raise_test_error"
    assert isinstance(event["line"], int)
    assert "ValueError: bad row" in event["traceback"]
    assert event["details"] == {"nm_id": 42}


def test_error_event_masks_secrets_and_truncates_large_values():
    try:
        raise RuntimeError("failure")
    except RuntimeError as exc:
        event = build_error_event(
            exc,
            phase="exchange",
            details={"Authorization": "secret-token", "payload": "x" * 3000},
        )

    assert event["details"]["Authorization"] == "***"
    assert event["details"]["payload"].endswith("[truncated]")


def test_success_result_is_reduced_to_counts():
    assert summarize_result([{"large": "payload"}, {"large": "payload"}]) == {
        "type": "list",
        "count": 2,
    }
    assert summarize_result({"rows": [1, 2, 3], "inserted": 2}) == {
        "rows": {"type": "list", "count": 3},
        "inserted": 2,
    }
