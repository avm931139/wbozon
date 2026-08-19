from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    WBCharacteristic,
    WBProduct,
    WBProductCharacteristic,
    WBProductDimensions,
    WBProductPhoto,
    WBProductSize,
    WBSizeBarcode,
    WBSubject,
)
from wb.services import product_service
from wb.services.product_service import ProductService


CARD = {
    "nmID": 123456,
    "imtID": 654321,
    "nmUUID": "11111111-1111-1111-1111-111111111111",
    "subjectID": 777,
    "subjectName": "Футболки",
    "vendorCode": "ABC-1",
    "brand": "Test brand",
    "title": "Test product",
    "description": "Description",
    "needKiz": True,
    "kizMarked": False,
    "createdAt": "2026-08-01T10:00:00Z",
    "updatedAt": "2026-08-02T10:00:00Z",
    "documents": {"items": [], "excludeDocuments": []},
    "photos": [{"big": "https://example.test/big.jpg", "tm": "https://example.test/tm.jpg"}],
    "dimensions": {"width": 10, "height": 20, "length": 30, "weightBrutto": 0.5, "isValid": True},
    "characteristics": [{"id": 1, "name": "Цвет", "value": ["Красный"]}],
    "sizes": [{"chrtID": 999, "techSize": "M", "wbSize": "46", "skus": ["200000000001"]}],
}


class FakeAPI:
    def list(self, **kwargs):
        return [CARD]


class TwoCardsAPI:
    def list(self, **kwargs):
        second = {
            **CARD,
            "nmID": 123457,
            "imtID": 654322,
            "nmUUID": "22222222-2222-2222-2222-222222222222",
            "vendorCode": "ABC-2",
            "sizes": [{"chrtID": 1000, "techSize": "L", "wbSize": "48", "skus": ["200000000002"]}],
        }
        return [CARD, second]


def test_product_service_persists_complete_card_idempotently(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(product_service, "SessionLocal", session_factory)

    service = ProductService()
    service.api = FakeAPI()
    service.sync_from_api()
    service.sync_from_api()

    with session_factory() as session:
        product = session.scalar(select(WBProduct))
        assert product.nm_id == CARD["nmID"]
        assert product.subject.name == "Футболки"
        assert product.dimensions.weight_brutto == 0.5
        assert product.characteristic_values[0].value == ["Красный"]
        assert product.sizes[0].barcodes[0].barcode == "200000000001"
        assert session.scalar(select(func.count()).select_from(WBProduct)) == 1
        assert session.scalar(select(func.count()).select_from(WBSubject)) == 1
        assert session.scalar(select(func.count()).select_from(WBProductPhoto)) == 1
        assert session.scalar(select(func.count()).select_from(WBProductDimensions)) == 1
        assert session.scalar(select(func.count()).select_from(WBCharacteristic)) == 1
        assert session.scalar(select(func.count()).select_from(WBProductCharacteristic)) == 1
        assert session.scalar(select(func.count()).select_from(WBProductSize)) == 1
        assert session.scalar(select(func.count()).select_from(WBSizeBarcode)) == 1


def test_product_service_reuses_shared_reference_rows(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(product_service, "SessionLocal", session_factory)

    service = ProductService()
    service.api = TwoCardsAPI()
    service.sync_from_api()

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(WBProduct)) == 2
        assert session.scalar(select(func.count()).select_from(WBSubject)) == 1
        assert session.scalar(select(func.count()).select_from(WBCharacteristic)) == 1
