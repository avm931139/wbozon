# Интеграция Яндекс Маркета

Пакет `yandex_market` получает справочники кабинета, каталог, заказы и складские
остатки из Partner API. Доменные задачи и остатки работают независимо: ошибка
каталога или заказов не блокирует остатки Яндекс Маркета, WB или Ozon.

Реализованные методы:

- `GET /v2/campaigns` — кабинеты и магазины;
- `POST /v2/businesses/{businessId}/warehouses` и `GET /v2/warehouses` — свои и FBY-склады;
- `POST /v2/businesses/{businessId}/offer-mappings` — каталог кабинета;
- `POST /v2/campaigns/{campaignId}/offers` — ассортимент магазина;
- `POST /v1/businesses/{businessId}/orders` — актуальная выборка заказов;
- `POST /v2/campaigns/{campaignId}/offers/stocks` — остатки по складам.
- `POST /v2/reports/boost-consolidated/generate` — буст продаж;
- `POST /v2/reports/shows-boost/generate` — буст показов;
- `POST /v2/reports/banners-statistics/generate` — охватное продвижение;
- `GET /v2/reports/info/{reportId}` — готовность и загрузка отчёта.

В production остатки запускаются постоянным процессом
`inventory_sync --marketplace yandex_market`: текущие строки обновляются каждый
час, а в `00:00 Europe/Moscow` создаётся независимый дневной срез.

Используется официальный метод `POST /v2/campaigns/{campaignId}/offers/stocks`: он доступен для всех моделей размещения и возвращает товары в разрезе складов. Запрос передаёт `withTurnover=true`, поэтому для FBY дополнительно сохраняются оценка оборачиваемости и количество дней запаса. Пагинация выполняется через `nextPageToken`, по 100 предложений на страницу.

## Настройка

```dotenv
YANDEX_MARKET_API_KEY=
YANDEX_MARKET_CAMPAIGN_IDS=12345678
YANDEX_MARKET_BUSINESS_ID=
YANDEX_MARKET_BASE_URL=https://api.partner.market.yandex.ru
YANDEX_MARKET_TIMEOUT_SECONDS=10
YANDEX_MARKET_HISTORY_FROM=2026-01-01
YANDEX_MARKET_ORDER_LOOKBACK_DAYS=30
YANDEX_MARKET_TIMEZONE=Europe/Moscow
YANDEX_MARKET_REQUIRED_TASKS=identity,catalog,orders,advertising,finances
YANDEX_MARKET_AD_POLL_SECONDS=5
YANDEX_MARKET_AD_POLL_ATTEMPTS=36
YANDEX_MARKET_AD_HISTORY_DAYS=90
YANDEX_MARKET_AD_REFRESH_DAYS=14
YANDEX_MARKET_AD_MAX_AGE_SECONDS=7200
YANDEX_MARKET_FINANCE_MAX_AGE_SECONDS=7200
```

Для нескольких магазинов перечислите campaign ID через запятую. `businessId`
обычно определяется автоматически через список магазинов; явное значение нужно
только как запасной вариант. Для полного текущего набора задач токену нужен
`all-methods:read-only` либо сочетание read-only-доступов к товарам и заказам.
Пока ключ или список кампаний не заполнены, workers Яндекс Маркета не включают.

После настройки:

```bash
python -m alembic upgrade head
python -m yandex_market --task identity
python -m yandex_market --task catalog
python -m yandex_market --task orders
python -m yandex_market --task advertising
python -m yandex_market --task finances
python -m inventory_sync --marketplace yandex_market --once
```

`advertising` независимо получает статистику буста продаж, буста показов и
охватного продвижения. Почасовой запуск сначала заполняет по одному самому новому
пропущенному дню за окно `YANDEX_MARKET_AD_HISTORY_DAYS` (по умолчанию 90 дней),
а после полного заполнения повторно обновляет последние
`YANDEX_MARKET_AD_REFRESH_DAYS` дней: атрибуция рекламы может дозревать после
первого получения отчёта. Для API-ключа нужен доступ
`promotion:read-only`, `finance-and-accounting` либо полный read-only доступ.
Асинхронные JSON-отчёты опрашиваются до готовности; ошибка задачи не откатывает
заказы, каталог или остатки. Если `YANDEX_MARKET_BUSINESS_ID` не задан, задача
использует единственный кабинет, ранее сохранённый заданием `identity`.

В оперативном дашборде расход Яндекс Маркета берётся не из неполного рекламного
среза, а из фактических рекламных списаний и удержаний отчёта
`united-netting`. Атрибутированная сумма заказов, ROAS и ДРР показываются только
когда все три рекламных отчёта покрывают каждый день выбранного периода.

`finances` каждый час формирует официальный JSON-отчёт по платежам
`/v2/reports/united-netting/generate`, сохраняет каждое начисление положительной
суммой, каждое удержание отрицательной и повторно сверяет последние семь дней.
Первый запуск загружает историю с `YANDEX_MARKET_HISTORY_FROM` блоками не более
90 дней. Данные находятся в `yandex_market_finance_transactions` и являются
источником выручки и расходов Яндекс Маркета в дашборде.

Первый запуск заказов загружает данные с `YANDEX_MARKET_HISTORY_FROM` отрезками
не более 30 дней между границами запроса. `date_to` бизнес-метода фактически не
включается в многодневную выдачу, поэтому соседние отрезки перекрываются этой
датой, а текущий день дополнительно запрашивается отдельным однодневным вызовом.
Переход на повторную проверку последних
`YANDEX_MARKET_ORDER_LOOKBACK_DAYS` происходит только после записи успешного
полного запуска с маркером `history_complete` в `yandex_market_sync_runs`.
Старые запуски без маркера автоматически инициируют однократный полный backfill.
Если первая историческая загрузка
оборвалась после сохранения нескольких отрезков, следующий запуск снова начинает
с `YANDEX_MARKET_HISTORY_FROM`; уже сохранённые заказы обновляются идемпотентно,
а исторический промежуток не теряется.

## Хранение

- `yandex_market_businesses` — кабинеты;
- `yandex_market_campaigns` — магазины и модели FBY/FBS;
- `yandex_market_warehouses` — партнёрские и фулфилмент-склады;
- `yandex_market_offers` — единый каталог кабинета;
- `yandex_market_campaign_offers` — состояние товара в конкретном магазине;
- `yandex_market_orders` — заголовки заказов и исходный ответ;
- `yandex_market_order_items` — позиции заказов;
- `yandex_market_sync_runs` — независимый журнал задач;
- `yandex_market_ad_daily_stats` — дневные показатели рекламы по источнику и кампании;
- `yandex_market_finance_transactions` — начисления и удержания отчёта по платежам;
- `yandex_market_stocks` и `yandex_market_stock_snapshots` — остатки.

Групповой почасовой Telegram-отчёт читает `yandex_market_orders` и показывает
заказы, товары, товарную сумму до комиссий (`payment + cashback + subsidy`),
модели FBY/FBS, доставки, отмены и возвраты за текущую московскую дату, а также
статус последнего задания `orders`. Блок остаётся в
сообщении при нуле строк и при ошибке загрузки. Личный operations bot сообщает
результат каждого задания и пояснение ошибки.

Постоянный systemd unit: `wbozon-inventory@yandex_market.service`. Если ключ или campaign IDs не настроены, этот unit не включают; отдельный worker завершится с ошибкой конфигурации вместо ложного успешного запуска с нулевыми строками.

Текущие данные хранятся в `yandex_market_stocks`, дневные срезы — в `yandex_market_stock_snapshots`. Логический ключ строки: `campaign_id + warehouse_id + offer_id + stock_type`. Пропавшие из полного ответа API строки сохраняются, но их `count` обнуляется.

Проверка:

```sql
SELECT campaign_id, warehouse_id, stock_type, COUNT(*) AS rows, SUM(count) AS quantity
FROM yandex_market_stocks
GROUP BY campaign_id, warehouse_id, stock_type
ORDER BY campaign_id, warehouse_id, stock_type;
```

Последние заказы:

```sql
SELECT order_id, campaign_id, program_type, status, created_at, items_count, total_amount
FROM yandex_market_orders
ORDER BY created_at DESC
LIMIT 100;
```

Контроль запусков:

```sql
SELECT task, status, started_at, finished_at, result, error
FROM yandex_market_sync_runs
ORDER BY started_at DESC
LIMIT 30;
```

Официальная документация: [получение остатков](https://yandex.ru/dev/market/partner-api/doc/ru/reference/stocks/getStocks), [авторизация по API-Key](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/authorization).

Полный проверенный каталог Partner API: [API_ENDPOINTS.md](API_ENDPOINTS.md).
