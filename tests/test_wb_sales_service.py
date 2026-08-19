from decimal import Decimal

from wb.services.sales_service import net_sales_amount, operation_type


def test_sale_id_prefix_defines_operation_without_overwriting_order():
    assert operation_type("S123") == "sale"
    assert operation_type("R123") == "return"
    assert operation_type("s123") == "sale"
    assert operation_type("anything") == "unknown"


def test_return_amount_reduces_net_regardless_of_wb_sign():
    assert net_sales_amount([Decimal("100"), Decimal("50")], [Decimal("-30")]) == (
        Decimal("150"), Decimal("30"), Decimal("120")
    )
    assert net_sales_amount([Decimal("100")], [Decimal("30")]) == (
        Decimal("100"), Decimal("30"), Decimal("70")
    )
