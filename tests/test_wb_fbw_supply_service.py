from datetime import date

from wb.exceptions import WBHTTPError
from wb.services.fbw_supply_service import FBWSupplyService


def test_supply_sync_continues_when_warehouse_directory_is_unavailable(monkeypatch):
    calls = []

    class API:
        def warehouses(self):
            calls.append("warehouses")
            raise WBHTTPError("temporarily disabled")

        def supplies(self, date_from, date_to):
            calls.append(("supplies", date_from, date_to))
            return []

    service = FBWSupplyService()
    service.api = API()
    monkeypatch.setattr(service, "_persist_warehouses", lambda rows: calls.append("persist_warehouses"))
    monkeypatch.setattr(service, "_persist_supply_list", lambda rows: [])

    result = service.sync_max_history()

    assert calls == ["warehouses", ("supplies", date(2019, 1, 1), date.today())]
    assert result == {
        "warehouses": 0,
        "warehouse_status": "unavailable",
        "warehouse_error": "WBHTTPError: temporarily disabled",
        "supplies": 0,
        "changed": 0,
        "goods": 0,
        "packages": 0,
    }


def test_supply_sync_still_persists_available_warehouse_directory(monkeypatch):
    warehouse_rows = [{"ID": 507, "name": "Warehouse"}]

    class API:
        def warehouses(self):
            return warehouse_rows

        def supplies(self, date_from, date_to):
            return []

    service = FBWSupplyService()
    service.api = API()
    persisted = []
    monkeypatch.setattr(service, "_persist_warehouses", lambda rows: persisted.extend(rows))
    monkeypatch.setattr(service, "_persist_supply_list", lambda rows: [])

    result = service.sync_max_history()

    assert persisted == warehouse_rows
    assert result["warehouses"] == 1
    assert result["warehouse_status"] == "completed"
    assert result["warehouse_error"] is None
