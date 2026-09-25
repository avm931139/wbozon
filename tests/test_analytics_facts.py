from datetime import date, datetime, timezone
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
    AnalyticsFactSyncRun,
    FactSale,
    FactSaleSource,
    FactAdvertisingDaily,
    FactProductEconomicsControl,
    FactProductEconomicsDaily,
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
    YandexMarketAdDailyStat,
    YandexMarketOffer,
)
from analytics_facts import service as fact_service
from analytics_facts.economics import (
    CALCULATION_VERSION,
    _is_logistics,
    allocate_kopecks,
    allocate_ozon_advertising,
)


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_product_economics_calculation_version_fits_database_columns():
    assert len(CALCULATION_VERSION) <= 30


def test_money_to_kopecks_uses_decimal_half_up():
    assert money_to_kopecks("1234.56") == 123456
    assert money_to_kopecks("10.005") == 1001
    assert money_to_kopecks("-10.005") == -1001


def test_cost_history_does_not_rewrite_older_periods():
    old = ProductCostRecord(
        id=1, unit_cost=Decimal("100"), currency="RUB",
        effective_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )
    changed = ProductCostRecord(
        id=2, unit_cost=Decimal("150"), currency="RUB",
        effective_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
    )
    history = [old, changed]

    # The first import is the baseline for dates before initial onboarding.
    assert FinancialSalesFactService._cost_for_date(history, date(2026, 8, 1)) is old
    assert FinancialSalesFactService._cost_for_date(history, date(2026, 9, 20)) is old
    assert FinancialSalesFactService._cost_for_date(history, date(2026, 9, 24)) is changed


def test_discount_refund_is_not_classified_as_return_logistics():
    assert not _is_logistics(
        "Скидка за лояльность Возврат скидки за участие в совместных акциях Возврат списания"
    )
    assert _is_logistics("Обратная логистика возврата товара")


def test_new_fact_run_closes_stale_running_attempts():
    session_factory = _session_factory()
    service = FinancialSalesFactService("wb", session_factory=session_factory)

    service._create_run("stale")
    service._create_run("current")

    with session_factory() as session:
        stale = session.get(AnalyticsFactSyncRun, "stale")
        current = session.get(AnalyticsFactSyncRun, "current")
        assert stale.status == "failed"
        assert stale.finished_at is not None
        assert "terminated" in stale.error
        assert current.status == "running"


def test_product_economics_allocation_never_loses_a_kopeck():
    allocated = allocate_kopecks(10001, {"a": 3, "b": 2, "c": 1})
    assert sum(allocated.values()) == 10001
    assert allocated["a"] > allocated["b"] > allocated["c"]
    negative = allocate_kopecks(-101, {"a": 1, "b": 1})
    assert sum(negative.values()) == -101


def test_ozon_campaign_only_advertising_is_allocated_without_losing_total():
    advertising, unallocated, method = allocate_ozon_advertising(
        10001,
        {"sku-a": 300, "sku-b": 100},
        {"sku-a": 1000, "sku-b": 0},
    )
    assert advertising == {"sku-a": 7751, "sku-b": 2250}
    assert sum(advertising.values()) == 10001
    assert unallocated == 0
    assert method == "direct_plus_revenue"


def test_ozon_advertising_without_sales_stays_explicitly_unallocated():
    advertising, unallocated, method = allocate_ozon_advertising(1234, {}, {})
    assert advertising == {}
    assert unallocated == 1234
    assert method == "allocated_by_revenue"


def test_unmatched_direct_advertising_is_not_allocated_to_other_products():
    advertising, unallocated, method = allocate_ozon_advertising(
        5000,
        {"sku-a": 10000},
        {"sku-a": 1000, "unallocated": 1500},
    )
    assert advertising == {"sku-a": 3500}
    assert unallocated == 1500
    assert method == "direct_plus_revenue"


def test_product_weight_allocation_is_kept_separate_from_direct_spend():
    advertising, unallocated, method = allocate_ozon_advertising(
        5000,
        {"sku-a": 10000, "sku-b": 5000},
        {"sku-a": 1000},
        {"sku-a": 2000, "sku-b": 1000},
    )
    assert sum(advertising.values()) == 5000
    assert unallocated == 0
    assert method == "product_weight_plus_revenue"


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
        for minute, (source_hash, transaction_type, source, quantity, amount) in enumerate(rows):
            session.add(YandexMarketFinanceTransaction(
                source_hash=source_hash, business_id=216, partner_id=10,
                # Cabinet components belonging to one order commonly arrive at
                # different minutes and still represent one sale/return event.
                transaction_at=now.replace(minute=minute), transaction_id=source_hash,
                transaction_type=transaction_type, transaction_source=source,
                order_id=7001, offer_id="SKU-1", product_or_service="Test product",
                quantity=quantity, amount=Decimal(amount),
                raw_data={"source": source_hash}, fetched_at=now,
            ))
        session.add(YandexMarketAdDailyStat(
            stat_date=now.date(), source="sales_boost", business_id=216,
            campaign_id=0, offer_id="", views=10, clicks=3, orders=1,
            spend=Decimal("10.00"), attributed_revenue=Decimal("90.00"),
            raw_data={"rows": [{
                "shopSku": "SKU-1", "showsWithFee": 10,
                "clicksVendorWithFee": 3, "orderItemsDeliveredWithFee": 1,
                "billedAmount": "10.00", "ordersGvmDeliveredWithFee": "90.00",
            }]}, fetched_at=now,
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
        "economics_rows": 1,
        "economics_control_days": 1,
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
        economics = session.scalar(select(FactProductEconomicsDaily))
        control = session.scalar(select(FactProductEconomicsControl))
        assert economics.revenue_kopecks == 7501
        assert economics.cost_kopecks == 4001
        assert economics.profit_kopecks == 3500
        assert economics.expense_allocation_method == "none"
        assert economics.advertising_allocation_method == "direct_plus_revenue"
        advertising = session.scalar(select(FactAdvertisingDaily))
        assert advertising.master_product_id == economics.master_product_id
        # Advertising attribution remains attached to the SKU, while accounting
        # spend is zero because this fixture has no finance-ledger ad charge.
        assert advertising.spend_kopecks == 0
        assert advertising.direct_spend_kopecks == 1000
        assert advertising.allocated_spend_kopecks == -1000
        assert advertising.views == 10
        assert advertising.clicks == 3
        assert advertising.orders == 1
        assert advertising.attributed_revenue_kopecks == 9000
        assert advertising.allocation_method == "direct_plus_revenue"
        assert control.revenue_kopecks == 7501
        assert control.profit_kopecks == 3500

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


def test_wb_product_expenses_stay_on_source_sku_and_residual_is_unallocated():
    session_factory = _session_factory()
    now = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
    sale_operation = next(iter(fact_service.WB_SALE_OPERATIONS))
    with session_factory() as session:
        products = []
        for index, (article, nm_id) in enumerate((("WB-A", 101), ("WB-B", 202)), start=1):
            master = MasterProduct(
                article=article, name=article, active=True,
                created_at=now, updated_at=now,
            )
            session.add(master)
            session.flush()
            session.add(MarketplaceProductLink(
                master_product_id=master.id, marketplace="wb", account_id="",
                external_product_id=str(nm_id), offer_id=article,
                source_article=article, normalized_article=article,
                match_method="exact", is_test_variant=False,
                active=True, matched_at=now,
            ))
            products.append((article, nm_id))
        report = WBFinancialSalesReport(
            report_wb_id=501, date_from=now, date_to=now, create_date=now,
            currency="RUB", report_type=1, raw_data={}, details_synced_at=now,
        )
        session.add(report)
        session.flush()
        session.add_all([
            WBFinancialSalesRow(
                report_id=report.id, rrd_id=11, nm_id=101, vendor_code="WB-A",
                seller_operation_name=sale_operation, sale_date=now, rr_date=now,
                quantity=1, retail_price_with_discount=Decimal("100"),
                for_pay=Decimal("60"), delivery_service=Decimal("10"),
                penalty=Decimal("5"), currency="RUB", raw_data={},
            ),
            WBFinancialSalesRow(
                report_id=report.id, rrd_id=12, nm_id=202, vendor_code="WB-B",
                seller_operation_name=sale_operation, sale_date=now, rr_date=now,
                quantity=1, retail_price_with_discount=Decimal("200"),
                for_pay=Decimal("150"), delivery_service=Decimal("20"),
                currency="RUB", raw_data={},
            ),
            WBFinancialSalesRow(
                report_id=report.id, rrd_id=13, seller_operation_name="adjustment",
                sale_date=now, rr_date=now, quantity=0,
                for_pay=Decimal("-30"), deduction=Decimal("10"),
                currency="RUB", raw_data={},
            ),
        ])
        session.commit()

    FinancialSalesFactService("wb", session_factory=session_factory).run()
    with session_factory() as session:
        rows = session.scalars(
            select(FactProductEconomicsDaily).order_by(
                FactProductEconomicsDaily.product_key
            )
        ).all()
        by_key = {row.seller_sku or "unallocated": row for row in rows}
        assert by_key["WB-A"].marketplace_expense_kopecks == 5500
        assert by_key["WB-A"].logistics_kopecks == 1000
        assert by_key["WB-A"].expense_allocation_method == "direct_financial_row"
        assert by_key["WB-B"].marketplace_expense_kopecks == 7000
        residual = next(row for row in rows if row.is_unallocated)
        assert residual.revenue_kopecks == -3000
        assert residual.marketplace_expense_kopecks == 1000
        assert residual.expense_allocation_method == "unallocated_financial_residual"
        control = session.scalar(select(FactProductEconomicsControl))
        assert control.revenue_kopecks == 27000
        assert control.marketplace_expense_kopecks == 13500
        assert control.profit_kopecks == 13500


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

