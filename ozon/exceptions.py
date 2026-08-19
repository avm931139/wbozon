class OzonError(RuntimeError):
    """Base Ozon integration error."""


class OzonAuthError(OzonError):
    pass


class OzonHTTPError(OzonError):
    pass


class OzonRateLimitError(OzonHTTPError):
    pass


class OzonParseError(OzonError):
    pass
