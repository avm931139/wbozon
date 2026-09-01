# Интеграция Ozon Seller API

Корневой пакет `ozon` — рабочий интеграционный слой Ozon Seller API и Ozon Performance API.

## Возможности

- загрузка списка и детальной информации о товарах;
- API агрегатных и складских остатков FBO/FBS; запись текущих значений и дневных срезов выполняет `inventory_sync`;
- загрузка отправлений FBS и FBO за настраиваемый период;
- загрузка поставок, ежедневная сверка отправленного и принятого FBO-количества,
  обращений покупателей, дневных продаж и финансовых операций;
- генерация, скачивание и хранение документов и бухгалтерских JSON-отчётов;
- загрузка кампаний и статистики рекламы через отдельный Ozon Performance API;
- построение дневного среза и месячного отчёта по сохранённым данным;
- идемпотентное сохранение в PostgreSQL;
- отдельный периодический запуск с изоляцией ошибок между разделами.

Исходные ответы сохраняются в `raw_data`, чтобы изменение контракта Ozon не приводило к потере полей.

## Структура

- `client.py` — HTTP, авторизация, повторы и ошибки;
- `endpoints.py` — пути Seller API;
- `products.py`, `stocks.py`, `warehouse_stocks.py`, `orders.py`, `supplies.py`, `communications.py`, `analytics.py`, `finances.py`, `accounting.py` — доменные API-модули Seller API;
- `accounting_storage.py` и `services/accounting_service.py` — безопасное хранение документов и бухгалтерских снимков;
- `services/supply_reconciliation_service.py` — состав FBO-поставок и фактическая приёмка по актам;
- `performance/` — OAuth-клиент, API и сервис рекламы;
- `services/` — синхронизация и нормализация;
- `repositories/` — поиск строк для idempotent upsert;
- `scheduler.py` — периодический цикл;
- `task_runner.py` — независимые задания, advisory lock и журнал `ozon_sync_runs`;
- `__main__.py` — команда `python -m ozon`.

## Настройка

Добавьте в `.env`:

```dotenv
OZON_CLIENT_ID=идентификатор_продавца
OZON_API_KEY=api_ключ
OZON_BASE_URL=https://api-seller.ozon.ru
OZON_TIMEOUT_SECONDS=30
OZON_SYNC_INTERVAL_SECONDS=21600
OZON_SYNC_RUN_ON_START=true
OZON_ORDER_LOOKBACK_DAYS=30
OZON_HISTORY_FROM=2026-01-01
OZON_SYNC_OVERLAP_DAYS=3
OZON_SUPPLY_REQUEST_PAUSE_SECONDS=0.25
OZON_SUPPLY_RECONCILIATION_FROM=2026-01-01
OZON_SUPPLY_RECONCILIATION_REQUEST_PAUSE_SECONDS=1.0
OZON_SUPPLY_RECONCILIATION_RATE_LIMIT_RETRIES=4
OZON_SUPPLY_RECONCILIATION_RATE_LIMIT_BACKOFF_SECONDS=30
OZON_TIMEZONE=Europe/Moscow
OZON_REQUIRED_TASKS=products,orders,supplies,daily_sales,finances,ads
OZON_ACCOUNTING_STORAGE_DIR=data/ozon/accounting
OZON_ACCOUNTING_HISTORY_FROM=2026-01-01
OZON_ACCOUNTING_DOWNLOAD_LIMIT=50
OZON_ACCOUNTING_MAX_FILE_BYTES=104857600
OZON_REPORT_ALLOWED_HOST_SUFFIXES=ozon.ru,ozone.ru
OZON_PERFORMANCE_CLIENT_ID=идентификатор_Performance_API
OZON_PERFORMANCE_CLIENT_SECRET=секрет_Performance_API
OZON_PERFORMANCE_BASE_URL=https://api-performance.ozon.ru
```

Затем примените миграцию:

```powershell
python -m alembic upgrade head
```

## Запуск

Один цикл:

```powershell
python -m ozon --once
```

Независимое задание с блокировкой от параллельного запуска и записью результата
в `ozon_sync_runs`:

```powershell
python -m ozon --task products
python -m ozon --task orders
python -m ozon --task supplies
python -m ozon --task supply_reconciliation
python -m ozon --supply-reconciliation-report
python -m ozon --task communications
python -m ozon --task daily_sales
python -m ozon --task finances
python -m ozon --task documents
python -m ozon --task ads
```

В production рекомендуется запускать отдельные задания через файлы из
[`deploy/systemd`](../deploy/systemd/README.md). Старые `--once` и постоянный `python -m ozon` сохранены для
ручной проверки и обратной совместимости.

Результат задания записывается компактно: коллекция превращается в `{"count": N}`, а составные результаты сохраняют отдельные счётчики. Если сервис вернул ключ вида `*_error`, задача получает статус `partial`, команда завершается кодом `1`, и healthcheck считает запуск неуспешным. Это не позволяет скрыть частично недоступный API за общим статусом `completed`.

Цикл выполняет разделы в порядке: товары, отправления, поставки, обращения, дневные продажи, финансы, документы и реклама. Ошибка одного раздела фиксируется в результате и не останавливает следующие разделы. Текущие остатки и их ежедневные срезы загружает отдельный worker `python -m inventory_sync --marketplace ozon`.

Задание `documents` независимо формирует бухгалтерские отчёты Ozon, сохраняет
JSON и скачивает готовые XLSX. Периоды, таблицы, защита временных ссылок и
production timer описаны в [`ACCOUNTING.md`](ACCOUNTING.md).
После первого успешного ручного запуска и включения timer добавьте `documents` в
`OZON_REQUIRED_TASKS`, чтобы healthcheck контролировал его статус и свежесть.

Задание `supply_reconciliation` ежедневно сопоставляет отправленное количество из
`/v1/supply-order/bundle` с фактической приёмкой из актов Ozon. Таблицы, запрос
расхождений и расписание описаны в
[`SUPPLY_RECONCILIATION.md`](SUPPLY_RECONCILIATION.md).

Если `OZON_PERFORMANCE_CLIENT_ID` и `OZON_PERFORMANCE_CLIENT_SECRET` не заданы, плановый цикл пропускает рекламу без ошибки. Команда `--sync-ads` по-прежнему требует оба реквизита.

Метод списка поставок Ozon не поддерживает фильтр по дате создания. Модуль получает идентификаторы поставок и применяет `OZON_HISTORY_FROM` после загрузки их детальной информации.
Между запросами деталей поставок выдерживается `OZON_SUPPLY_REQUEST_PAUSE_SECONDS`, чтобы снизить вероятность HTTP 429.

Задание `communications` синхронизирует Questions и Reviews независимо. На текущем кабинете Questions доступны, а Reviews возвращают HTTP 403, поэтому timer `communications` оставлен выключенным и не входит в `OZON_REQUIRED_TASKS`. После выдачи доступа задача должна завершиться без `reviews_error`; только после этого её следует включать в production-набор.

Ежедневный отчёт строится из сохранённого дневного среза, а месячный — как сумма этих дневных строк:

```powershell
python -m ozon --report-day 2026-08-08
python -m ozon --report-month 2026-08
```

Только синхронизация рекламы Ozon Performance:

```powershell
python -m ozon --sync-ads
```

Постоянное расписание:

```powershell
python -m ozon
```

Ozon запускается отдельно от корневого `main.py`. Данные его ежедневного среза остатков используются Excel-отчётом `python -m telegram_bot --once stock-files`; остальные Telegram-отчёты пока ориентированы на WB.

Складская детализация Ozon хранится в `ozon_warehouse_stocks`, справочник складов — в `ozon_warehouses`, ежедневная история — в `ozon_warehouse_stock_snapshots`. Совместимые агрегаты продолжают храниться в `ozon_stocks` и `ozon_stock_snapshots`. Подробные endpoint’ы, ключи таблиц, правила сверки и время фиксации описаны в [архитектуре складских остатков](WAREHOUSE_STOCK_ARCHITECTURE.md) и [документации `inventory_sync`](../inventory_sync/README.md).
