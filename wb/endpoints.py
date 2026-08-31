"""Centralized and structured Wildberries API endpoints."""


class WBProductsEndpoints:
    """Endpoints for products and cards."""

    LIST = "/content/v2/get/cards/list"


class WBWarehousesEndpoints:
    """Endpoints for warehouses."""

    LIST = "/api/v3/warehouses"


class WBStocksEndpoints:
    """Endpoints for stocks."""

    LIST = "/api/v3/stocks/{warehouse_id}"


class WBFboStocksEndpoints:
    LIST = "/api/analytics/v1/stocks-report/wb-warehouses"


class WBOrdersEndpoints:
    FBS_LIST = "/api/v3/orders"
    FBS_STATUS = "/api/v3/orders/status"
    HISTORY = "/api/v1/supplier/orders"


class WBCategoriesEndpoints:
    """Endpoints for categories and groups."""

    LIST = "/content/v2/object/all"


class WBDocumentsEndpoints:
    CATEGORIES = "/api/v1/documents/categories"
    LIST = "/api/v1/documents/list"
    DOWNLOAD = "/api/v1/documents/download"
    DOWNLOAD_ALL = "/api/v1/documents/download/all"


class WBFinanceEndpoints:
    BALANCE = "/api/v1/account/balance"


class WBEndpoints:
    """Compatibility facade for existing imports."""

    PRODUCTS_LIST = WBProductsEndpoints.LIST
    WAREHOUSES_LIST = WBWarehousesEndpoints.LIST
    STOCKS_LIST = WBStocksEndpoints.LIST
    FBO_STOCKS_LIST = WBFboStocksEndpoints.LIST
    FBS_ORDERS_LIST = WBOrdersEndpoints.FBS_LIST
    FBS_ORDERS_STATUS = WBOrdersEndpoints.FBS_STATUS
    ORDERS_HISTORY = WBOrdersEndpoints.HISTORY
    CATEGORIES_LIST = WBCategoriesEndpoints.LIST
    DOCUMENT_CATEGORIES = WBDocumentsEndpoints.CATEGORIES
    DOCUMENTS_LIST = WBDocumentsEndpoints.LIST
    DOCUMENT_DOWNLOAD = WBDocumentsEndpoints.DOWNLOAD
    DOCUMENTS_DOWNLOAD_ALL = WBDocumentsEndpoints.DOWNLOAD_ALL
    ACCOUNT_BALANCE = WBFinanceEndpoints.BALANCE
