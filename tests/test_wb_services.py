from wb.services.sync_service import WBSyncService


def test_sync_service_initializes_api_modules():
    service = WBSyncService()
    assert service.products_api is not None
    assert service.warehouses_api is not None
    assert service.stocks_api is not None
    assert service.categories_api is not None
    assert service.fbo_stocks_api is not None


def test_sync_service_delegates_to_persisting_services(monkeypatch):
    service = WBSyncService()
    calls = []

    monkeypatch.setattr(
        service.product_service,
        "sync_from_api",
        lambda **kwargs: calls.append(("products", kwargs)) or [],
    )
    monkeypatch.setattr(
        service.warehouse_service,
        "sync_from_api",
        lambda **kwargs: calls.append(("warehouses", kwargs)) or [],
    )
    monkeypatch.setattr(
        service.stock_service,
        "sync_from_api",
        lambda **kwargs: calls.append(("stocks", kwargs)) or [],
    )
    monkeypatch.setattr(
        service.category_service,
        "sync_from_api",
        lambda **kwargs: calls.append(("categories", kwargs)) or [],
    )
    monkeypatch.setattr(
        service.fbo_stock_service,
        "sync_from_api",
        lambda **kwargs: calls.append(("fbo_stocks", kwargs)) or [],
    )

    service.sync_products(limit=10)
    service.sync_warehouses()
    service.sync_stocks(warehouse_id=1, chrt_ids=[2])
    service.sync_categories(locale="ru")
    service.sync_fbo_stocks(limit=100)

    assert calls == [
        ("products", {"limit": 10}),
        ("warehouses", {}),
        ("stocks", {"warehouse_id": 1, "chrt_ids": [2]}),
        ("categories", {"locale": "ru"}),
        ("fbo_stocks", {"limit": 100}),
    ]
