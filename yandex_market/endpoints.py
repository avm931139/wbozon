"""Partner API paths used by the implemented Yandex Market domains."""

CAMPAIGNS = "/v2/campaigns"
FULFILLMENT_WAREHOUSES = "/v2/warehouses"


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
