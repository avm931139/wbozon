class WBError(Exception):
    """Базовое исключение для WB integration."""


class WBAuthError(WBError):
    """Ошибка авторизации/доступа."""


class WBRateLimitError(WBError):
    """Превышен лимит запросов."""


class WBHTTPError(WBError):
    """HTTP ошибка."""


class WBParseError(WBError):
    """Ошибка разбора ответа API."""
