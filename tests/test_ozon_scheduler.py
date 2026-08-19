from ozon.scheduler import OzonPeriodicSync


class Service:
    def __init__(self):
        self.calls = []

    def sync_products(self):
        self.calls.append("products")
        return [1]

    def sync_orders(self):
        self.calls.append("orders")
        return {"fbs": 1, "fbo": 2}

    def sync_supplies(self):
        self.calls.append("supplies")
        return 3

    def sync_communications(self):
        self.calls.append("communications")
        return {"reviews": 4, "questions": 5}

    def sync_daily_sales(self):
        self.calls.append("daily_sales")
        return 6

    def sync_finances(self):
        self.calls.append("finances")
        return 7

    def sync_ads(self):
        self.calls.append("ads")
        return {"campaigns": 8, "daily_stats": 9}


def test_cycle_keeps_independent_tasks_running():
    service = Service()
    result = OzonPeriodicSync(service, interval_seconds=60).run_cycle()
    assert service.calls == ["products", "orders", "supplies", "communications", "daily_sales", "finances", "ads"]
    assert result["products"]["status"] == "ok"
    assert result["orders"]["status"] == "ok"
    assert result["supplies"]["status"] == "ok"
    assert result["communications"]["status"] == "ok"
    assert result["daily_sales"]["status"] == "ok"
    assert result["finances"]["status"] == "ok"
    assert result["ads"]["status"] == "ok"
