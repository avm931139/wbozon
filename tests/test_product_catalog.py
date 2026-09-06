from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    MarketplaceProductAttribute,
    MarketplaceProductCatalogSnapshot,
    MarketplaceProductLink,
    MarketplaceProductMedia,
    MasterProduct,
    OzonProduct,
    ProductCatalogSyncRun,
    WBProduct,
    WBProductPhoto,
    YandexMarketOffer,
)
from product_catalog.service import ProductCatalogService
from product_catalog.storage import ProductMediaStorage


class FakeResponse:
    def __init__(self, content=b"image-bytes", content_type="image/jpeg"):
        self.content = content
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(content)),
        }

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.content


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self):
        return None


def test_media_storage_downloads_atomically_and_verifies(tmp_path):
    session = FakeSession(FakeResponse())
    storage = ProductMediaStorage(
        tmp_path,
        max_file_bytes=100,
        timeout=5,
        session_factory=lambda: session,
    )

    stored = storage.download(
        url="https://cdn.example.test/photo?id=1",
        marketplace="wb",
        article="../../NVL0012",
        external_product_id="101",
        media_type="image",
        position=0,
        source_key="a" * 64,
    )

    assert stored.extension == "jpg"
    assert stored.size == len(b"image-bytes")
    assert ".." not in stored.relative_path
    assert storage.verify(stored.relative_path, size=stored.size, sha256=stored.sha256)
    assert session.calls[0][1]["stream"] is True


def test_media_storage_rejects_wrong_content_and_size(tmp_path):
    html = ProductMediaStorage(
        tmp_path / "html",
        session_factory=lambda: FakeSession(FakeResponse(b"html", "text/html")),
    )
    with pytest.raises(ValueError, match="HTML"):
        html.download(
            url="https://example.test/file",
            marketplace="wb",
            article="SKU",
            external_product_id="1",
            media_type="image",
            position=0,
            source_key="b" * 64,
        )

    large = ProductMediaStorage(
        tmp_path / "large",
        max_file_bytes=2,
        session_factory=lambda: FakeSession(FakeResponse(b"large")),
    )
    with pytest.raises(ValueError, match="size limit"):
        large.download(
            url="https://example.test/file.jpg",
            marketplace="wb",
            article="SKU",
            external_product_id="1",
            media_type="image",
            position=0,
            source_key="c" * 64,
        )


def test_catalog_normalization_is_idempotent_and_keeps_change_snapshots(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        master = MasterProduct(
            article="NVL0012", name="Product", active=True, created_at=now, updated_at=now
        )
        session.add(master)
        session.flush()
        wb = WBProduct(
            nm_id=101,
            vendor_code="NVL0012",
            title="WB product",
            raw_data={"vendorCode": "NVL0012"},
        )
        wb.photos.append(WBProductPhoto(
            position=0,
            big_url="https://cdn.test/wb.jpg",
            c246x328_url="https://cdn.test/wb-small.jpg",
            c516x688_url="https://cdn.test/wb-medium.jpg",
            hq_url="https://cdn.test/wb-hq.jpg",
            square_url="https://cdn.test/wb-square.jpg",
            tm_url="https://cdn.test/wb-thumb.jpg",
        ))
        ozon = OzonProduct(
            product_id=202,
            offer_id="NVL0012_D",
            name="Ozon product",
            raw_data={
                "primary_image": "https://cdn.test/ozon-main.jpg",
                "images": ["https://cdn.test/ozon-main.jpg", "https://cdn.test/ozon-2.jpg"],
                "attributes": [{"id": 10, "name": "Color", "values": ["white"]}],
            },
            created_at=now,
            updated_at=now,
        )
        yandex = YandexMarketOffer(
            business_id=303,
            offer_id="NVL0012_D",
            name="Yandex product",
            barcodes=[],
            pictures=["https://cdn.test/yandex.jpg"],
            raw_data={
                "offer": {
                    "parameterValues": [{"id": 20, "name": "Power", "value": 54}]
                }
            },
            fetched_at=now,
        )
        session.add_all([wb, ozon, yandex])
        session.flush()
        session.add_all([
            MarketplaceProductLink(
                master_product_id=master.id,
                marketplace="wb",
                account_id="",
                external_product_id="101",
                offer_id="NVL0012",
                source_article="NVL0012",
                normalized_article="NVL0012",
                match_method="exact",
                is_test_variant=False,
                active=True,
                matched_at=now,
            ),
            MarketplaceProductLink(
                master_product_id=master.id,
                marketplace="yandex_market",
                account_id="303",
                external_product_id="NVL0012_D",
                offer_id="NVL0012_D",
                source_article="NVL0012_D",
                normalized_article="NVL0012_D",
                match_method="suffix",
                is_test_variant=True,
                active=True,
                matched_at=now,
            ),
        ])
        session.commit()

    storage = ProductMediaStorage(tmp_path)
    service = ProductCatalogService(
        session_factory=session_factory,
        storage=storage,
        workers=1,
    )
    first = service.run(download=False)
    second = service.run(download=False)

    assert first["result"]["source_rows"] == 3
    assert first["result"]["media_rows"] == 4
    assert first["result"]["attribute_rows"] == 2
    assert first["result"]["snapshots_created"] == 3
    assert second["result"]["snapshots_created"] == 0
    with session_factory() as session:
        assert session.query(MarketplaceProductMedia).count() == 4
        assert session.query(MarketplaceProductAttribute).count() == 2
        assert session.query(MarketplaceProductCatalogSnapshot).count() == 3
        assert session.query(ProductCatalogSyncRun).count() == 2
        yandex_media = session.query(MarketplaceProductMedia).filter_by(
            marketplace="yandex_market"
        ).one()
        assert yandex_media.master_product_id is not None
        wb_media = session.query(MarketplaceProductMedia).filter_by(marketplace="wb").one()
        assert wb_media.role == "big"
        assert wb_media.source_url == "https://cdn.test/wb.jpg"
