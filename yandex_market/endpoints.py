"""Partner API paths used by the implemented Yandex Market domains."""

CAMPAIGNS = "/v2/campaigns"
FULFILLMENT_WAREHOUSES = "/v2/warehouses"
REPORT_INFO = "/v2/reports/info/{report_id}"

AD_REPORT_PATHS = {
    "sales_boost": "/v2/reports/boost-consolidated/generate",
    "shows_boost": "/v2/reports/shows-boost/generate",
    "shelves": "/v2/reports/shelf-statistics/generate",
    "banners": "/v2/reports/banners-statistics/generate",
}


def partner_warehouses(business_id: int) -> str:
    return f"/v2/businesses/{business_id}/warehouses"


def offer_mappings(business_id: int) -> str:
    return f"/v2/businesses/{business_id}/offer-mappings"


def campaign_offers(campaign_id: int) -> str:
    return f"/v2/campaigns/{campaign_id}/offers"


def campaign_stocks(campaign_id: int) -> str:
    return f"/v2/campaigns/{campaign_id}/offers/stocks"


def business_orders(business_id: int) -> str:
    return f"/v1/businesses/{business_id}/orders"


def business_prices(business_id: int) -> str:
    return f"/v2/businesses/{business_id}/offer-prices"
