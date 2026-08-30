class YandexMarketError(RuntimeError):
    """Base error for the Yandex Market integration."""


class YandexMarketAuthError(YandexMarketError):
    pass


class YandexMarketHTTPError(YandexMarketError):
    pass


class YandexMarketRateLimitError(YandexMarketHTTPError):
    pass


class YandexMarketParseError(YandexMarketError):
    pass
