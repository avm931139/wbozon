# Остатки Яндекс Маркета

Пакет `yandex_market` получает складские остатки из Partner API. В production он работает отдельным процессом `inventory_sync --marketplace yandex_market`: текущие строки обновляются каждый час, а в `00:00 Europe/Moscow` создаётся независимый дневной срез. Ошибка Яндекс Маркета не блокирует остатки WB и Ozon.

Используется официальный метод `POST /v2/campaigns/{campaignId}/offers/stocks`: он доступен для всех моделей размещения и возвращает товары в разрезе складов. Пагинация выполняется через `nextPageToken`, по 100 предложений на страницу.

## Настройка

```dotenv
YANDEX_MARKET_API_KEY=
YANDEX_MARKET_CAMPAIGN_IDS=12345678
YANDEX_MARKET_BASE_URL=https://api.partner.market.yandex.ru
YANDEX_MARKET_TIMEOUT_SECONDS=10
```

Для нескольких магазинов перечислите campaign ID через запятую. Токену достаточно read-only-доступа `offers-and-cards-management:read-only` или `all-methods:read-only`. Пока ключ или список кампаний не заполнены, worker Яндекс Маркета не включают; WB и Ozon от него не зависят.

После настройки:

```bash
python -m alembic upgrade head
python -m inventory_sync --marketplace yandex_market --once
```

Постоянный systemd unit: `wbozon-inventory@yandex_market.service`. Если ключ или campaign IDs не настроены, этот unit не включают; отдельный worker завершится с ошибкой конфигурации вместо ложного успешного запуска с нулевыми строками.

Текущие данные хранятся в `yandex_market_stocks`, дневные срезы — в `yandex_market_stock_snapshots`. Логический ключ строки: `campaign_id + warehouse_id + offer_id + stock_type`. Пропавшие из полного ответа API строки сохраняются, но их `count` обнуляется.

Проверка:

```sql
SELECT campaign_id, warehouse_id, stock_type, COUNT(*) AS rows, SUM(count) AS quantity
FROM yandex_market_stocks
GROUP BY campaign_id, warehouse_id, stock_type
ORDER BY campaign_id, warehouse_id, stock_type;
```

Официальная документация: [получение остатков](https://yandex.ru/dev/market/partner-api/doc/ru/reference/stocks/getStocks), [авторизация по API-Key](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/authorization).

Полный проверенный каталог Partner API: [API_ENDPOINTS.md](API_ENDPOINTS.md).
