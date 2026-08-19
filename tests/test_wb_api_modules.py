import pytest
from datetime import date, datetime, timezone

from wb.categories import CategoriesAPI
from wb.fbo_stocks import FBOStocksAPI
from wb.finances import FinancesAPI
from wb.customer_communications import CustomerCommunicationsAPI
from wb.promotion import PromotionAPI
from wb.orders import FBSOrdersAPI, OrdersHistoryAPI
from wb.products import ProductsAPI
from wb.stocks import StocksAPI
from wb.sales import SalesOperationsAPI
from wb.warehouses import WarehousesAPI


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, path, *, params=None, retries=3):
        self.calls.append(("GET", path, params, None))
        return self.response

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append(("POST", path, None, json_body))
        return self.response


class SequenceClient(FakeClient):
    def __init__(self, responses):
        super().__init__(None)
        self.responses = iter(responses)

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append(("POST", path, None, json_body))
        return next(self.responses)


def test_products_use_content_cards_contract():
    client = FakeClient({"cards": [{"nmID": 1}], "cursor": {"total": 1}})

    result = ProductsAPI(client).list(settings={"cursor": {"limit": 100}})

    assert result == [{"nmID": 1}]
    assert client.calls == [
        (
            "POST",
            "/content/v2/get/cards/list",
            None,
            {"settings": {"cursor": {"limit": 100}}},
        )
    ]


def test_products_follow_cursor_pagination():
    client = SequenceClient(
        [
            {
                "cards": [{"nmID": 1}],
                "cursor": {"total": 1, "updatedAt": "first", "nmID": 1},
            },
            {
                "cards": [],
                "cursor": {"total": 0, "updatedAt": "first", "nmID": 1},
            },
        ]
    )

    result = ProductsAPI(client).list(settings={"cursor": {"limit": 1}})

    assert result == [{"nmID": 1}]
    assert client.calls[1][3] == {
        "settings": {"cursor": {"limit": 1, "updatedAt": "first", "nmID": 1}}
    }


def test_warehouses_accept_top_level_list():
    client = FakeClient([{"id": 1, "name": "Main"}])

    result = WarehousesAPI(client).list()

    assert result == [{"id": 1, "name": "Main"}]
    assert client.calls == [("GET", "/api/v3/warehouses", {}, None)]


def test_categories_extract_data_list():
    client = FakeClient({"data": [{"id": 1, "name": "Subject"}]})

    result = CategoriesAPI(client).list(locale="ru")

    assert result == [{"id": 1, "name": "Subject"}]
    assert client.calls == [("GET", "/content/v2/object/all", {"locale": "ru"}, None)]


def test_stocks_use_warehouse_path_and_chrt_ids_body():
    client = FakeClient({"stocks": [{"chrtId": 10, "amount": 3}]})

    result = StocksAPI(client).list(warehouse_id=7, chrt_ids=[10])

    assert result == [{"chrtId": 10, "amount": 3, "warehouseId": 7}]
    assert client.calls == [
        ("POST", "/api/v3/stocks/7", None, {"chrtIds": [10]})
    ]


def test_stocks_require_warehouse_and_chrt_ids():
    api = StocksAPI(FakeClient({"stocks": []}))

    with pytest.raises(ValueError, match="warehouse_id"):
        api.list(chrt_ids=[])
    with pytest.raises(ValueError, match="chrt_ids"):
        api.list(warehouse_id=7)


def test_fbo_stocks_use_analytics_contract():
    client = FakeClient({"data": {"items": [{"warehouseId": 507, "chrtId": 10, "quantity": 3}]}})

    result = FBOStocksAPI(client).list(limit=100)

    assert result == [{"warehouseId": 507, "chrtId": 10, "quantity": 3}]
    assert client.calls == [
        (
            "POST",
            "/api/analytics/v1/stocks-report/wb-warehouses",
            None,
            {"nmIds": [], "chrtIds": [], "limit": 100, "offset": 0},
        )
    ]


def test_fbs_orders_use_period_and_pagination_contract():
    client = FakeClient({"next": 0, "orders": [{"id": 1}]})
    date_from = datetime(2026, 8, 1, tzinfo=timezone.utc)
    date_to = datetime(2026, 8, 2, tzinfo=timezone.utc)

    result = FBSOrdersAPI(client).list(date_from, date_to)

    assert result == [{"id": 1}]
    assert client.calls == [("GET", "/api/v3/orders", {
        "limit": 1000,
        "next": 0,
        "dateFrom": int(date_from.timestamp()),
        "dateTo": int(date_to.timestamp()),
    }, None)]


def test_order_history_requests_earliest_date():
    client = FakeClient([{"srid": "one"}])

    result = OrdersHistoryAPI(client).list("2019-01-01")

    assert result == [{"srid": "one"}]
    assert client.calls == [("GET", "/api/v1/supplier/orders", {"dateFrom": "2019-01-01", "flag": 0}, None)]


def test_finance_sales_reports_use_current_v1_contract():
    client = FakeClient([{"reportId": 1}])

    result = FinancesAPI(client).sales_reports(date(2025, 1, 1), date(2025, 1, 31))

    assert result == [{"reportId": 1}]
    assert client.calls == [("POST", "/api/finance/v1/sales-reports/list", None, {
        "dateFrom": "2025-01-01", "dateTo": "2025-01-31", "period": "weekly", "limit": 100, "offset": 0,
    })]


def test_finance_details_follow_rrd_pagination():
    client = SequenceClient([[{"rrdId": 10}], []])

    result = FinancesAPI(client).sales_details_by_report(7, limit=1)

    assert result == [{"rrdId": 10}]
    assert client.calls[0][3] == {"limit": 1, "rrdId": 0}
    assert client.calls[1][3] == {"limit": 1, "rrdId": 10}


def test_customer_questions_are_strictly_read_only_get_requests():
    client = FakeClient({"data": {"questions": [{"id": "q1"}]}})

    result = CustomerCommunicationsAPI(client).questions(False, take=100)

    assert result == [{"id": "q1"}]
    assert client.calls == [("GET", "/api/v1/questions", {
        "isAnswered": "false", "take": 100, "skip": 0, "order": "dateDesc",
    }, None)]


def test_promotion_expenses_use_read_only_cost_history_contract():
    client = FakeClient([{"updNum": 1}])
    result = PromotionAPI(client).expenses(date(2026, 8, 1), date(2026, 8, 9))
    assert result == [{"updNum": 1}]
    assert client.calls == [("GET", "/adv/v1/upd", {"from": "2026-08-01", "to": "2026-08-09"}, None)]


def test_promotion_finance_uses_read_only_contracts():
    client = FakeClient({"balance": 100})
    api = PromotionAPI(client)

    assert api.balance() == {"balance": 100}
    api.campaign_budget(42)

    assert client.calls == [
        ("GET", "/adv/v1/balance", None, None),
        ("GET", "/adv/v1/budget", {"id": 42}, None),
    ]


def test_promotion_campaign_details_use_current_v2_contract():
    client = FakeClient({"adverts": [{"id": 42}]})

    result = PromotionAPI(client).campaign_details([42])

    assert result == [{"id": 42}]
    assert client.calls == [("GET", "/api/advert/v2/adverts", {"ids": "42"}, None)]


def test_promotion_fullstats_enforces_official_20_second_interval():
    now = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    client = FakeClient([])
    api = PromotionAPI(client, clock=lambda: now[0], sleeper=sleep)

    api.full_stats([1], date(2026, 8, 1), date(2026, 8, 2))
    api.full_stats([2], date(2026, 8, 1), date(2026, 8, 2))

    assert sleeps == [20.0]


def test_operational_sales_use_statistics_contract_and_shared_rate_limit():
    now = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    client = FakeClient([])
    api = SalesOperationsAPI(client, clock=lambda: now[0], sleeper=sleep)

    api.orders(date(2026, 8, 1))
    api.sales(date(2026, 8, 1))

    assert client.calls == [
        ("GET", "/api/v1/supplier/orders", {"dateFrom": "2026-08-01", "flag": 0}, None),
        ("GET", "/api/v1/supplier/sales", {"dateFrom": "2026-08-01", "flag": 0}, None),
    ]
    assert sleeps == [60.0]
