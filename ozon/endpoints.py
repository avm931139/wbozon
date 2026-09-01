class OzonEndpoints:
    PRODUCT_LIST = "/v3/product/list"
    PRODUCT_INFO_LIST = "/v3/product/info/list"
    STOCKS = "/v4/product/info/stocks"
    FBO_STOCKS_BY_WAREHOUSE = "/v1/product/info/stocks-by-warehouse/fbo"
    FBS_STOCKS_BY_WAREHOUSE = "/v2/product/info/stocks-by-warehouse/fbs"
    ANALYTICS_STOCKS = "/v1/analytics/stocks"
    WAREHOUSE_STOCK_REPORT = "/v2/analytics/stock_on_warehouses"
    FBS_POSTINGS = "/v4/posting/fbs/list"
    FBO_POSTINGS = "/v3/posting/fbo/list"
    REVIEWS = "/v2/review/list"
    QUESTIONS = "/v1/question/list"


class OzonAccountingEndpoints:
    REPORT_LIST = "/v1/report/list"
    REPORT_INFO = "/v1/report/info"
    COMPENSATION = "/v1/finance/compensation"
    DECOMPENSATION = "/v1/finance/decompensation"
    DOCUMENT_B2B_SALES = "/v1/finance/document-b2b-sales"
    DOCUMENT_B2B_SALES_JSON = "/v1/finance/document-b2b-sales/json"
    MUTUAL_SETTLEMENT = "/v1/finance/mutual-settlement"
    PRODUCTS_BUYOUT = "/v1/finance/products/buyout"
    REALIZATION_POSTING = "/v1/finance/realization/posting"
    REALIZATION_POSTING_REPORT = "/v1/report/realization/posting/create"
    REALIZATION = "/v2/finance/realization"
    BALANCE = "/v1/finance/balance"
    CASH_FLOW = "/v1/finance/cash-flow-statement/list"


class OzonSupplyReconciliationEndpoints:
    BUNDLE = "/v1/supply-order/bundle"
    ACT_SUMMARY = "/v1/supply-order/act/summary/get"
    ACT_PRODUCTS = "/v1/supply-order/act/product/get"
