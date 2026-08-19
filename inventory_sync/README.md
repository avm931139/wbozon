# Периодическая синхронизация остатков

Пакет `inventory_sync` независимо загружает текущие остатки WB FBS, WB FBO и Ozon и создаёт ежедневные исторические срезы.

Остатки исключены из общих циклов `WBPeriodicSync` и `OzonPeriodicSync`. Для регулярного обновления `python -m inventory_sync` должен работать как отдельный постоянно запущенный процесс или сервис.

## Расписание

С 17 августа 2026 года Ozon возвращает аналитические остатки в реальном времени. Фиксированного времени публикации дневных данных у Ozon больше нет: прежние 07:00 и 16:00 UTC отменены. Поэтому `01:00 Europe/Moscow` — бизнес-время среза проекта, а не задержка ожидания публикации Ozon.

- текущие остатки обновляются с интервалом `INVENTORY_SYNC_INTERVAL_SECONDS` (по умолчанию каждый час);
- ежедневный срез выполняется в `INVENTORY_SNAPSHOT_TIME` (по умолчанию `01:00`);
- расчёт времени всегда выполняется в `INVENTORY_TIMEZONE` (по умолчанию `Europe/Moscow`) независимо от времени сервера;
- после запуска позже 01:00 отсутствующий срез за текущую московскую дату создаётся сразу;
- уникальные ограничения и журнал запусков защищают от повторного среза за один день.

`INVENTORY_SYNC_RUN_ON_START=true` запускает обычное обновление сразу при старте. Эта настройка не отключает догоняющий ежедневный срез: если после 01:00 среза за текущую московскую дату нет, он выполняется независимо от `INVENTORY_SYNC_RUN_ON_START`.

При ошибке API срез не создаётся частично. Ошибка записывается в `inventory_sync_runs`, а планировщик повторяет попытку на следующем часовом интервале.

## Настройки

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `INVENTORY_SYNC_INTERVAL_SECONDS` | интервал обновления текущих остатков | `3600` |
| `INVENTORY_SNAPSHOT_TIME` | московское время ежедневного среза в формате `HH:MM` | `01:00` |
| `INVENTORY_TIMEZONE` | временная зона расписания и даты среза | `Europe/Moscow` |
| `INVENTORY_SYNC_RUN_ON_START` | немедленное обычное обновление после запуска | `true` |

## Запуск

```powershell
python -m alembic upgrade head
python -m inventory_sync
```

Разовое обновление текущих остатков:

```powershell
python -m inventory_sync --once
```

Ручной срез за текущую московскую дату:

```powershell
python -m inventory_sync --snapshot
```

`--snapshot` сначала заново выполняет все обязательные этапы загрузки, поэтому это не копирование потенциально устаревших текущих таблиц. Если завершённый срез за текущую московскую дату уже существует, команда возвращает `skipped` без запросов к API.

## Источники и текущие таблицы

| Источник | API | Текущая таблица | Логический ключ |
|---|---|---|---|
| WB FBS | Marketplace API `/api/v3/stocks/{warehouse_id}` | `wb_fbs_stocks` | `sku + warehouse_id` |
| WB FBO | Seller Analytics `/api/analytics/v1/stocks-report/wb-warehouses` | `wb_fbo_stocks` | `size_id + warehouse_id` |
| Ozon | Seller API `/v4/product/info/stocks` | `ozon_stocks` | `product_id + stock_type` |
| Ozon FBO по складам | Seller API `/v1/product/info/stocks-by-warehouse/fbo` | `ozon_warehouse_stocks` | `product_id + warehouse_id + stock_type` |
| Ozon FBS по складам | Seller API `/v2/product/info/stocks-by-warehouse/fbs` | `ozon_warehouse_stocks` | `product_id + warehouse_id + stock_type` |

`ozon_warehouses` хранит внешний `ozon_warehouse_id`, название и кластер. Названия и кластеры обогащаются через `/v1/analytics/stocks`; временная ошибка этого вспомогательного запроса не блокирует запись количеств. Агрегат `/v4/product/info/stocks` сохраняется параллельно и сверяется с суммой складских строк. Поскольку оба источника realtime и запрашиваются последовательно, кратковременное расхождение фиксируется предупреждением, но не приводит к потере полного складского ответа.

WB FBS требует предварительно загруженные `wb_product_sizes` и `wb_fbs_warehouses`. Если каталог размеров или склады отсутствуют, запуск завершается ошибкой, не изменяя текущие остатки и историю.

Все обязательные ответы сначала полностью загружаются из API. После успешной загрузки текущие таблицы и, при ежедневном запуске, исторические таблицы записываются одной транзакцией. Исчезнувшие позиции не удаляются: их количественные поля обнуляются, а в `raw_data` добавляется `zeroed_by_inventory_sync=true`.

Успешный `--once` возвращает четыре счётчика: `wb_fbs`, `wb_fbo`, `ozon` для агрегатных строк и `ozon_warehouse` для строк по складам.

## Проверка Ozon в PostgreSQL

Текущие суммы и число складов:

```sql
SELECT
    s.stock_type,
    COUNT(*) AS rows,
    COUNT(DISTINCT s.warehouse_id) AS warehouses,
    SUM(s.present) AS present,
    SUM(s.reserved) AS reserved
FROM ozon_warehouse_stocks AS s
GROUP BY s.stock_type
ORDER BY s.stock_type;
```

Остатки с названием склада:

```sql
SELECT
    s.product_id,
    s.offer_id,
    s.sku,
    s.stock_type,
    w.ozon_warehouse_id,
    w.name AS warehouse_name,
    w.cluster_name,
    s.present,
    s.reserved,
    s.fetched_at
FROM ozon_warehouse_stocks AS s
JOIN ozon_warehouses AS w ON w.id = s.warehouse_id
ORDER BY s.offer_id, s.stock_type, w.name;
```

Дневной складской срез проверяется тем же соединением с таблицей `ozon_warehouse_stock_snapshots` и фильтром по `snapshot_date`.

## Исторические срезы

| Таблица | Уникальность строки за день | Количественные поля |
|---|---|---|
| `wb_fbs_stock_snapshots` | `snapshot_date + sku + warehouse_id` | `quantity` |
| `wb_fbo_stock_snapshots` | `snapshot_date + size_id + warehouse_id` | `quantity`, `in_way_to_client`, `in_way_from_client` |
| `ozon_stock_snapshots` | `snapshot_date + product_id + stock_type` | `present`, `reserved` |
| `ozon_warehouse_stock_snapshots` | `snapshot_date + product_id + warehouse_id + stock_type` | `present`, `reserved` |

`snapshot_date` — календарная дата в `INVENTORY_TIMEZONE`. `captured_at` — единый timezone-aware момент фактического получения среза; PostgreSQL хранит его как `TIMESTAMP WITH TIME ZONE`. Догоняющий срез поэтому может иметь, например, `snapshot_date=2026-08-17` и фактический `captured_at` позже 01:00.

В срез попадают и активные, и обнулённые ранее известные комбинации. Это позволяет отличать нулевой остаток от отсутствующей связи товара со складом.

## Журнал и защита от параллельного запуска

`inventory_sync_runs` хранит:

- тип запуска `periodic` или `daily_snapshot`;
- плановое и фактическое время;
- дату ежедневного среза;
- статус `running`, `completed` или `failed`;
- количество принятых строк WB FBS, WB FBO, агрегата Ozon и Ozon по складам;
- текст ошибки.

Перед обращением к API процесс получает PostgreSQL advisory lock. Второй экземпляр не начинает параллельную загрузку и получает `InventorySyncAlreadyRunning`. Блокировка не заменяет запуск процесса под supervisor/systemd/Docker с политикой перезапуска.
