from unittest.mock import Mock

from supply_movement_report.collectors import yandex_movements


def test_yandex_campaign_ids_use_parsed_config_tuple(monkeypatch):
    client = Mock()
    client.post.return_value = {"result": {"requests": [], "paging": {}}}
    monkeypatch.setattr("supply_movement_report.collectors.YANDEX_MARKET_CAMPAIGN_IDS", (149007825, 149010920))
    monkeypatch.setattr("supply_movement_report.collectors.YandexMarketClient", lambda: client)

    assert yandex_movements(None, None) == ([], [])
    assert client.post.call_count == 2
