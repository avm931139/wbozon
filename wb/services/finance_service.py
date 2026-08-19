from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db import SessionLocal
from app.models import (
    WBFinancialAcquiringReport,
    WBFinancialAcquiringRow,
    WBFinancialSalesReport,
    WBFinancialSalesRow,
    WBProduct,
)
from wb.finances import FinancesAPI


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


class FinanceService:
    def __init__(self):
        self.api = FinancesAPI()

    def sync_sales_reports(self, date_from: date = date(2025, 1, 1), date_to: date | None = None) -> int:
        rows = self.api.sales_reports(date_from, date_to or date.today())
        with SessionLocal() as session:
            existing = {x.report_wb_id: x for x in session.query(WBFinancialSalesReport).all()}
            for item in rows:
                report_id = int(item["reportId"])
                row = existing.get(report_id)
                if row is None:
                    row = WBFinancialSalesReport(report_wb_id=report_id)
                    session.add(row)
                self._map_sales_report(row, item)
            session.commit()
        return len(rows)

    def sync_sales_details(self, date_from: date = date(2024, 1, 29), date_to: date | None = None) -> int:
        rows = self.api.sales_details(date_from, date_to or date.today())
        with SessionLocal() as session:
            reports = {x.report_wb_id: x for x in session.query(WBFinancialSalesReport).all()}
            products = {x.nm_id: x.id for x in session.query(WBProduct).all()}
            existing = {x.rrd_id: x for x in session.query(WBFinancialSalesRow).all()}
            touched: set[int] = set()
            for item in rows:
                report_wb_id = int(item["reportId"])
                report = reports.get(report_wb_id)
                if report is None:
                    report = WBFinancialSalesReport(report_wb_id=report_wb_id)
                    self._map_sales_report(report, item)
                    session.add(report); session.flush(); reports[report_wb_id] = report
                rrd_id = int(item["rrdId"])
                row = existing.get(rrd_id)
                if row is None:
                    row = WBFinancialSalesRow(report=report, rrd_id=rrd_id, raw_data=item)
                    session.add(row)
                self._map_sales_row(row, item, products)
                touched.add(report.id)
            now = datetime.utcnow()
            for report in reports.values():
                if report.id in touched:
                    report.details_synced_at = now
            session.commit()
        return len(rows)

    def sync_acquiring_reports(self, date_from: date = date(2025, 1, 1), date_to: date | None = None) -> int:
        rows = self.api.acquiring_reports(date_from, date_to or date.today())
        with SessionLocal() as session:
            existing = {x.report_wb_id: x for x in session.query(WBFinancialAcquiringReport).all()}
            for item in rows:
                report_id = int(item["reportId"]); row = existing.get(report_id)
                if row is None:
                    row = WBFinancialAcquiringReport(report_wb_id=report_id); session.add(row)
                row.seller_finance_name = item.get("sellerFinanceName"); row.date_from = _dt(item.get("dateFrom")); row.date_to = _dt(item.get("dateTo")); row.create_date = _dt(item.get("createDate"))
                row.currency = item.get("currency") or "RUB"; row.acquiring_fee_sum = _money(item.get("acquiringFeeSum")); row.acquiring_fee_vat_sum = _money(item.get("acquiringFeeVatSum")); row.raw_data = item
            session.commit()
        return len(rows)

    def sync_acquiring_details(self, date_from: date = date(2025, 1, 1), date_to: date | None = None) -> int:
        rows = self.api.acquiring_details(date_from, date_to or date.today())
        with SessionLocal() as session:
            reports = {x.report_wb_id: x for x in session.query(WBFinancialAcquiringReport).all()}
            existing = {x.rrd_id: x for x in session.query(WBFinancialAcquiringRow).all()}
            touched: set[int] = set()
            for item in rows:
                report = reports.get(int(item["reportId"]))
                if report is None:
                    continue
                rrd_id = int(item["rrdId"]); row = existing.get(rrd_id)
                if row is None:
                    row = WBFinancialAcquiringRow(report=report, rrd_id=rrd_id, raw_data=item); session.add(row)
                row.nm_id = item.get("nmId"); row.srid = item.get("srid"); row.shk_id = item.get("shkId"); row.acquiring_bank = item.get("acquiringBank")
                row.document_type = item.get("documentType"); row.invoice_number = item.get("invoiceNumber"); row.currency = item.get("currency")
                row.operation_sign = -1 if str(row.document_type or "").casefold() == "возврат" else 1
                row.retail_amount = _money(item.get("retailAmount")); row.acquiring_fee = _money(item.get("acquiringFee")); row.acquiring_fee_vat = _money(item.get("acquiringFeeVat"))
                row.signed_retail_amount = row.retail_amount * row.operation_sign
                row.signed_acquiring_fee = row.acquiring_fee * row.operation_sign
                row.signed_acquiring_fee_vat = row.acquiring_fee_vat * row.operation_sign
                row.transaction_date = _dt(item.get("acqDate")); row.sale_date = _dt(item.get("saleDate")); row.invoice_date = _dt(item.get("invoiceDate")); row.raw_data = item
                touched.add(report.id)
            now = datetime.utcnow()
            for report in reports.values():
                if report.id in touched: report.details_synced_at = now
            session.commit()
        return len(rows)

    @staticmethod
    def _map_sales_report(row: WBFinancialSalesReport, item: dict[str, Any]) -> None:
        row.seller_finance_name = item.get("sellerFinanceName"); row.date_from = _dt(item.get("dateFrom")); row.date_to = _dt(item.get("dateTo")); row.create_date = _dt(item.get("createDate"))
        row.currency = item.get("currency") or "RUB"; row.report_type = int(item.get("reportType") or 0)
        for attr, key in (("retail_amount_sum", "retailAmountSum"), ("for_pay_sum", "forPaySum"), ("delivery_service_sum", "deliveryServiceSum"), ("paid_storage_sum", "paidStorageSum"), ("paid_acceptance_sum", "paidAcceptanceSum"), ("deduction_sum", "deductionSum"), ("penalty_sum", "penaltySum"), ("additional_payment_sum", "additionalPaymentSum"), ("bank_payment_sum", "bankPaymentSum")):
            setattr(row, attr, _money(item.get(key)))
        row.raw_data = item

    @staticmethod
    def _map_sales_row(row: WBFinancialSalesRow, item: dict[str, Any], products: dict[int, int]) -> None:
        nm_id = int(item.get("nmId") or 0); row.nm_id = nm_id or None; row.product_id = products.get(nm_id)
        row.order_id = item.get("orderId"); row.order_uid = item.get("orderUid"); row.srid = item.get("srid"); row.shk_id = item.get("shkId"); row.sku = item.get("sku")
        row.vendor_code = item.get("vendorCode"); row.title = item.get("title"); row.subject_name = item.get("subjectName"); row.brand_name = item.get("brandName"); row.tech_size = item.get("techSize"); row.seller_operation_name = item.get("sellerOperName")
        row.order_date = _dt(item.get("orderDt")); row.sale_date = _dt(item.get("saleDt")); row.rr_date = _dt(item.get("rrDate")); row.quantity = int(item.get("quantity") or 0); row.currency = item.get("currency")
        for attr, key in (("retail_price", "retailPrice"), ("retail_amount", "retailAmount"), ("retail_price_with_discount", "retailPriceWithDisc"), ("for_pay", "forPay"), ("delivery_service", "deliveryService"), ("acquiring_fee", "acquiringFee"), ("ppvz_sales_commission", "ppvzSalesCommission"), ("ppvz_reward", "ppvzReward"), ("penalty", "penalty"), ("additional_payment", "additionalPayment"), ("rebill_logistic_cost", "rebillLogisticCost"), ("paid_storage", "paidStorage"), ("deduction", "deduction"), ("paid_acceptance", "paidAcceptance")):
            setattr(row, attr, _money(item.get(key)))
        row.raw_data = item
