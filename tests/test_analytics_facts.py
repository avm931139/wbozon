from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from analytics_facts.service import (
    FinancialSalesFactService,
    PendingFact,
    money_to_kopecks,
)
from app.db import Base
from app.models import (
    FactSale,
    FactSaleSource,
    MarketplaceProductLink,
    MasterProduct,
    OzonFinanceAccrualType,
    OzonFinancePostingAccrual,
    OzonPosting,
    OzonProduct,
    ProductBarcode,
    ProductCostImportRun,
    ProductCostRecord,
    WBFinancialSalesReport,
    WBFinancialSalesRow,
    YandexMarketFinanceTransaction,
    YandexMarketOffer,
)
from analytics_facts import service as fact_service


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_money_to_kopecks_uses_decimal_half_up():
    assert money_to_kopecks("1234.56") == 123456
    assert money_to_kopecks("10.005") == 1001
    assert money_to_kopecks("-10.005") == -1001


def test_kopeck_reconciliation_preserves_group_control_total():
    rows = [
        PendingFact({
            "account_id": "cabinet", "business_date": datetime(2026, 8, 1).date(),
            "currency": "RUB", "source_event_key": str(index),
            "unit_price_exact": Decimal("10.005"), "unit_cost_exact": None,
            "gross_amount_exact": Decimal("10.005"),
            "discount_amount_exact": Decimal("0"),
            "marketplace_discount_exact": Decimal("0"),
            "customer_paid_exact": Decimal("0"),
            "sales_amount_exact": Decimal("10.005"),
            "return_amount_exact": Decimal("0"),
            "compensation_amount_exact": Decimal("0"),
            "net_revenue_exact": Decimal("10.005"),
            "cost_amount_exact": None,
        }, [])
        for index in range(2)
    ]

    FinancialSalesFactService._assign_kopecks(rows)

    assert sum(row.values["net_revenue_kopecks"] for row in rows) == 2001
    assert sorted(row.values["net_revenue_kopecks"] for row in rows) == [1000, 1001]


def test_yandex_financial_components_become_one_sale_and_one_return_fact():
    session_factory = _session_factory()
    now = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        master = MasterProduct(
            article="SKU-1", name="Test product", active=True,
            created_at=now, updated_at=now,
        )
        session.add(master)
        session.flush()
        link = MarketplaceProductLink(
            master_product_id=master.id,
            marketplace="yandex_market", account_id="216",
            external_product_id="SKU-1", offer_id="SKU-1",
            source_article="SKU-1", normalized_article="SKU-1",
            match_method="exact", is_test_variant=False,
            product_name="Test product", active=True, matched_at=now,
        )
        run = ProductCostImportRun(
            id="cost-run", source_file="cost.xlsx", source_sha256="a" * 64,
            started_at=now, finished_at=now, status="completed",
            rows_total=1, rows_imported=1, rows_skipped_blank=0,
        )
        session.add_all([link, run])
        session.flush()
        session.add(ProductCostRecord(
            import_run_id=run.id, master_product_id=master.id,
            article="SKU-1", product_name="Test product",
            unit_cost=Decimal("40.005"), quantity=10, currency="RUB",
            effective_at=now, source_row=2, created_at=now,
        ))
        session.add(YandexMarketOffer(
            business_id=216, offer_id="SKU-1", market_sku=9001,
            name="Test product", barcodes=["111", "222"], pictures=[],
            raw_data={}, fetched_at=now,
        ))
        rows = [
            ("s1", "Начисление", "Платёж покупателя", 2, "100.00"),
            ("s2", "Начисление", "Баллы за скидку Маркета", 2, "50.01"),
            ("r1", "Возврат", "Возврат платежа покупателя", 1, "-60.00"),
            ("r2", "Возврат", "Возврат баллов за скидку Маркета", 1, "-15.00"),
        ]
        for source_hash, transaction_type, source, quantity, amount in rows:
            session.add(YandexMarketFinanceTransaction(
                source_hash=source_hash, business_id=216, partner_id=10,
                transaction_at=now, transaction_id=source_hash,
                transaction_type=transaction_type, transaction_source=source,
                order_id=7001, offer_id="SKU-1", product_or_service="Test product",
                quantity=quantity, amount=Decimal(amount),
                raw_data={"source": source_hash}, fetched_at=now,
            ))
        session.commit()

    result = FinancialSalesFactService(
        "yandex_market", session_factory=session_factory
    ).run()["result"]

    assert result == {
        "source_rows": 4,
        "facts_written": 2,
        "lineage_rows": 4,
        "barcode_rows": 2,
        "unmatched_products": 0,
    }
    with session_factory() as session:
        facts = session.scalars(select(FactSale).order_by(FactSale.event_type)).all()
        sale = next(row for row in facts if row.event_type == "sale")
        returned = next(row for row in facts if row.event_type == "return")
        assert sale.quantity == 2
        assert returned.quantity == -1
        assert sale.net_revenue_kopecks == 15001
        assert returned.net_revenue_kopecks == -7500
        assert sale.marketplace_discount_kopecks == 5001
        assert sale.customer_paid_kopecks == 10000
        assert sale.cost_amount_kopecks == 8001
        assert returned.cost_amount_kopecks == -4000
        assert sum(row.cost_amount_kopecks for row in facts) == 4001
        assert session.scalar(select(func.count()).select_from(FactSaleSource)) == 4
        assert session.scalar(select(func.count()).select_from(ProductBarcode)) == 2

    # A full rebuild is idempotent and does not duplicate facts or barcodes.
    FinancialSalesFactService("yandex_market", session_factory=session_factory).run()
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FactSale)) == 2
        assert session.scalar(select(func.count()).select_from(ProductBarcode)) == 2


def test_wb_financial_sale_and_return_use_signed_values():
    session_factory = _session_factory()
    now = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        master = MasterProduct(
            article="WB-1", name="WB product", active=True,
            created_at=now, updated_at=now,
        )
        session.add(master)
        session.flush()
        session.add(MarketplaceProductLink(
            master_product_id=master.id, marketplace="wb", account_id="",
            external_product_id="101", offer_id="WB-1", source_article="WB-1",
            normalized_article="WB-1", match_method="exact",
            is_test_variant=False, active=True, matched_at=now,
        ))
        report = WBFinancialSalesReport(
            report_wb_id=500, date_from=now, date_to=now, create_date=now,
            currency="RUB", report_type=1, raw_data={}, details_synced_at=now,
        )
        session.add(report)
        session.flush()
        for rrd_id, operation in ((1, "Продажа"), (2, "Возврат")):
            session.add(WBFinancialSalesRow(
                report_id=report.id, rrd_id=rrd_id, nm_id=101,
                vendor_code="WB-1", seller_operation_name=operation,
                sale_date=now, rr_date=now, quantity=2,
                retail_price_with_discount=Decimal("99.995"),
                currency="RUB", raw_data={"rrd_id": rrd_id},
            ))
        session.commit()

    result = FinancialSalesFactService("wb", session_factory=session_factory).run()["result"]
    assert result["facts_written"] == 2
    with session_factory() as session:
        facts = session.scalars(select(FactSale).order_by(FactSale.event_type)).all()
        sale = next(row for row in facts if row.event_type == "sale")
        returned = next(row for row in facts if row.event_type == "return")
        assert sale.quantity == 2
        assert returned.quantity == -2
        assert sale.sales_amount_kopecks == 19999
        assert returned.return_amount_kopecks == -19999
        assert sum(row.net_revenue_kopecks for row in facts) == 0


def test_ozon_posting_finance_uses_product_link_and_all_catalog_barcodes(monkeypatch):
    session_factory = _session_factory()
    now = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(fact_service, "OZON_CLIENT_ID", "client-1")
    with session_factory() as session:
        master = MasterProduct(
            article="OZ-1", name="Ozon product", active=True,
            created_at=now, updated_at=now,
        )
        session.add(master)
        session.flush()
        session.add(MarketplaceProductLink(
            master_product_id=master.id, marketplace="ozon", account_id="client-1",
            external_product_id="202", offer_id="OZ-1", source_article="OZ-1",
            normalized_article="OZ-1", match_method="exact",
            is_test_variant=False, active=True, matched_at=now,
        ))
        operation_type = OzonFinanceAccrualType(
            type_id=10, name="SaleCommission", description="Sale",
            raw_data={}, fetched_at=now,
        )
        product = OzonProduct(
            product_id=202, offer_id="OZ-1", name="Ozon product", sku=303,
            barcode="333", raw_data={"barcodes": ["333", "444"]},
            created_at=now, updated_at=now,
        )
        session.add_all([operation_type, product])
        session.flush()
        session.add(OzonFinancePostingAccrual(
            source_hash="b" * 64, posting_number="posting-1",
            accrual_date=now.date(), type_id=10, sku=303, quantity=1,
            seller_price=Decimal("-250.005"), accrued=Decimal("-50"),
            currency="RUB", raw_data={"posting": "posting-1"}, fetched_at=now,
        ))
        session.commit()

    result = FinancialSalesFactService("ozon", session_factory=session_factory).run()["result"]
    assert result["facts_written"] == 1
    assert result["barcode_rows"] == 2
    with session_factory() as session:
        fact = session.scalar(select(FactSale))
        assert fact.event_type == "return"
        assert fact.quantity == -1
        assert fact.net_revenue_kopecks == -25001
        assert fact.master_product_id is not None


def test_ozon_old_sku_uses_confirmed_offer_from_saved_posting(monkeypatch):
    session_factory = _session_factory()
    now = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(fact_service, "OZON_CLIENT_ID", "client-1")
    with session_factory() as session:
        master = MasterProduct(
            article="OLD-1", name="Historical Ozon product", active=True,
            created_at=now, updated_at=now,
        )
        session.add(master)
        session.flush()
        session.add(MarketplaceProductLink(
            master_product_id=master.id, marketplace="ozon", account_id="client-1",
            external_product_id="current-product-id", offer_id="OLD-1",
            source_article="OLD-1", normalized_article="OLD-1",
            match_method="exact", is_test_variant=False, active=True,
            matched_at=now,
        ))
        session.add(OzonFinanceAccrualType(
            type_id=10, name="SaleCommission", description="Sale",
            raw_data={}, fetched_at=now,
        ))
        session.add(OzonPosting(
            posting_number="old-posting", order_id=1, order_number="1",
            scheme="fbo", status="delivered", substatus=None,
            in_process_at=now, shipment_date=now,
            products=[{"sku": 999, "offer_id": "OLD-1", "name": "Old item"}],
            analytics_data=None, financial_data=None, raw_data={},
            created_at=now, updated_at=now,
        ))
        session.add(OzonFinancePostingAccrual(
            source_hash="c" * 64, posting_number="old-posting",
            accrual_date=now.date(), type_id=10, sku=999, quantity=1,
            seller_price=Decimal("123.45"), accrued=Decimal("10"),
            currency="RUB", raw_data={"posting": "old-posting"}, fetched_at=now,
        ))
        session.commit()

    result = FinancialSalesFactService("ozon", session_factory=session_factory).run()["result"]
    assert result["unmatched_products"] == 0
    with session_factory() as session:
        fact = session.scalar(select(FactSale))
        assert fact.master_product_id is not None
        assert fact.seller_sku == "OLD-1"
        assert fact.offer_id == "OLD-1"
        assert fact.marketplace_sku == "999"
        assert fact.fulfillment_type == "fbo"

