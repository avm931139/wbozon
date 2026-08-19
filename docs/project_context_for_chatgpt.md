# Контекст проекта для AI-ассистентов

## Цель

`wbozon` — рабочее приложение для загрузки данных Wildberries и Ozon в PostgreSQL и отправки аналитических отчётов в Telegram.

## Актуальная архитектура

- `app/` — конфигурация, подключение к БД и ORM-модели;
- `wb/` — основной интеграционный слой Wildberries;
- `ozon/` — интеграционный слой Ozon Seller/Performance API с независимыми jobs для каталога, логистики, обращений, продаж, финансов и рекламы;
- `inventory_sync/` — отдельный процесс текущих остатков WB/Ozon, складской детализации Ozon и ежедневных срезов в 00:00 `Europe/Moscow`;
- `telegram_bot/` — корневой пакет Telegram-отчётов;
- `healthcheck/` — проверка systemd/cron, свежести inventory и обязательных Ozon jobs, дневных срезов и доставки Telegram с дедуплицированными оповещениями;
- `main.py` — совместный запуск синхронизации WB и Telegram-отчётов; production-задачи Ozon запускаются через `python -m ozon --task <name>` и systemd timers;
- `alembic/` — единственный основной механизм эволюции схемы;
- `tests/` — актуальные тесты новой архитектуры.

Папка `legacy_core/` является унаследованной/справочной. Не следует подключать её к основному процессу или переносить из неё код без отдельного решения о миграции.

## Поток данных

```text
WB API → wb API class → service → repository/session → app.models → PostgreSQL
Ozon API → ozon task runner → service → repository/session → app.models + ozon_sync_runs → PostgreSQL
WB/Ozon stock APIs → inventory_sync → current stocks + aggregate and warehouse daily snapshots
Telegram API ← telegram_bot / healthcheck ← PostgreSQL
```

Ozon warehouse inventory uses `/v1/product/info/stocks-by-warehouse/fbo` and `/v2/product/info/stocks-by-warehouse/fbs`. Current rows are stored in `ozon_warehouse_stocks`, warehouse metadata in `ozon_warehouses`, and daily rows in `ozon_warehouse_stock_snapshots`. The legacy-compatible aggregate remains in `ozon_stocks` and `ozon_stock_snapshots`. Since 2026-08-17 Ozon stock analytics are realtime; `00:00 Europe/Moscow` is the application's business cutoff.

Production Ozon jobs: `products`, `orders`, `supplies`, `communications`,
`daily_sales`, `finances`, `ads`. Они запускаются независимо, используют
PostgreSQL advisory lock для защиты от пересечения и записывают результат в
`ozon_sync_runs`. Бизнес-дата Ozon рассчитывается в `OZON_TIMEZONE`, по умолчанию
`Europe/Moscow`.

## Ключевые ограничения

- не выводить значения `.env`, токены или авторизационные заголовки;
- не придумывать поля API: моделировать по реальным ответам WB;
- сохранять идемпотентность повторных синхронизаций;
- не смешивать транспорт, бизнес-логику и persistence;
- использовать timezone-aware даты для нового кода;
- не менять унаследованный код без явной необходимости;
- после изменения импортов проверять точки запуска: `python main.py --help`, `python -m telegram_bot --help`, `python -m ozon --help`, `python -m inventory_sync --help` и `python -m healthcheck`.

## Проверки перед завершением изменений

```powershell
python -m pytest -q
python -m alembic heads
```

Дополнительная документация: [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md), [`../wb/README.md`](../wb/README.md), [`../ozon/README.md`](../ozon/README.md), [`../inventory_sync/README.md`](../inventory_sync/README.md), [`../telegram_bot/README.md`](../telegram_bot/README.md).
