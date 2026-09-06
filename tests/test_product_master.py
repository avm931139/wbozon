from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketplaceProductLink, MasterProduct, ProductMappingRun
from product_master.service import (
    ProductMappingService,
    SourceProduct,
    match_article,
    normalize_article,
)


class StubMappingService(ProductMappingService):
    def __init__(self, sources, **kwargs):
        super().__init__(**kwargs)
        self.sources = sources

    def _source_products(self):
        return list(self.sources)


def source(marketplace, external_id, article, name=None, account_id=""):
    return SourceProduct(
        marketplace=marketplace,
        account_id=account_id,
        external_product_id=external_id,
        offer_id=article,
        article=article,
        name=name,
    )


def test_article_normalization_and_conservative_suffix_matching():
    known = {"NVL0022", "NVL0022_DD", "MODEL_D"}
    assert normalize_article("  nvl0022  ") == "NVL0022"
    assert match_article("NVL0022_DD", known) == ("NVL0022", "suffix")
    assert match_article("MODEL_D", known) == ("MODEL_D", "exact")
    assert match_article("UNKNOWN_TEST", known) == ("UNKNOWN_TEST", "exact")


def test_mapping_groups_exact_articles_and_known_test_suffixes_idempotently():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    sources = [
        source("wb", "101", "NVL0022", "WB name"),
        source("ozon", "202", "NVL0022_DD", "Ozon test"),
        source("yandex_market", "NVL0022", "nvl0022", "Yandex name", "303"),
        source("ozon", "204", "ONLY_D", "No known base"),
    ]
    service = StubMappingService(sources, session_factory=session_factory)

    first = service.run()
    second = service.run()

    assert first["result"] == {
        "source_rows": 4,
        "master_products": 2,
        "exact_links": 3,
        "suffix_links": 1,
        "inactive_links": 0,
    }
    assert second["result"] == first["result"]
    with session_factory() as session:
        assert session.query(MasterProduct).count() == 2
        assert session.query(MarketplaceProductLink).count() == 4
        assert session.query(ProductMappingRun).count() == 2
        base = session.query(MasterProduct).filter_by(article="NVL0022").one()
        linked = session.query(MarketplaceProductLink).filter_by(
            marketplace="ozon", external_product_id="202"
        ).one()
        assert linked.master_product_id == base.id
        assert linked.match_method == "suffix"
        assert linked.is_test_variant is True


def test_manual_mapping_is_not_overwritten():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        manual_master = MasterProduct(
            article="MANUAL", name="Manual", active=True, created_at=now, updated_at=now
        )
        automatic_master = MasterProduct(
            article="NVL0022", name="Automatic", active=True, created_at=now, updated_at=now
        )
        session.add_all([manual_master, automatic_master])
        session.flush()
        session.add(MarketplaceProductLink(
            master_product_id=manual_master.id,
            marketplace="ozon",
            account_id="",
            external_product_id="202",
            offer_id="NVL0022_D",
            source_article="NVL0022_D",
            normalized_article="NVL0022_D",
            match_method="manual",
            is_test_variant=False,
            active=True,
            matched_at=now,
        ))
        session.commit()

    service = StubMappingService([
        source("wb", "101", "NVL0022"),
        source("ozon", "202", "NVL0022_D"),
    ], session_factory=session_factory)
    service.run()

    with session_factory() as session:
        link = session.query(MarketplaceProductLink).filter_by(
            marketplace="ozon", external_product_id="202"
        ).one()
        assert link.master_product_id == session.query(MasterProduct).filter_by(
            article="MANUAL"
        ).one().id
        assert link.match_method == "manual"
