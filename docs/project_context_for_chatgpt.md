# Контекст проекта для AI-ассистентов

## Цель

`wbozon` — рабочее приложение для загрузки данных Wildberries, Ozon и Яндекс Маркета в PostgreSQL и отправки аналитических отчётов в Telegram.

## Актуальная архитектура

- `app/` — конфигурация, подключение к БД и ORM-модели;
- `wb/` — основной интеграционный слой Wildberries и независимый worker документов/баланса;
- `ozon/` — интеграционный слой Ozon Seller/Performance API с независимыми jobs для каталога, логистики, обращений, продаж, финансов, документов и рекламы;
- `yandex_market/` — Partner API Яндекс Маркета;
- `inventory_sync/` — отдельные workers `wb`, `ozon`, `yandex_market` для текущих остатков и ежедневных срезов в 00:00 `Europe/Moscow`;
- `telegram_bot/` — корневой пакет Telegram-отчётов;
- `operations_bot/` — независимый личный дайджест событий из журналов PostgreSQL с долговечной очередью;
- `healthcheck/` — проверка systemd workers, свежести inventory и обязательных Ozon jobs, дневных срезов и доставки Telegram с дедуплицированными оповещениями;
- `main.py` — совместимый alias для `python -m wb`; он не запускает Telegram;
- `deploy/systemd/` — канонические units постоянных workers и timers;
- `alembic/` — единственный основной механизм эволюции схемы;
- `tests/` — актуальные тесты новой архитектуры.

Папка `legacy_core/` является унаследованной/справочной. Не следует подключать её к основному процессу или переносить из неё код без отдельного решения о миграции.

## Поток данных

```text
WB API → wb API class → service → repository/session → app.models → PostgreSQL
WB Documents/Finance API → wb.document_sync → files + wb_document_sync_runs → PostgreSQL
Ozon API → ozon task runner → service → repository/session → app.models + ozon_sync_runs → PostgreSQL
WB/Ozon/Yandex stock APIs → separate inventory workers → current stocks + daily snapshots
Telegram API ← telegram_bot / healthcheck ← PostgreSQL
Private Telegram ← operations_bot ← sync journals + durable operations queue
```

Проект — модульный монолит с независимыми процессами и общей PostgreSQL, не набор сетевых микросервисов. Workers не вызывают друг друга напрямую. Каноническое описание: [`ARCHITECTURE.md`](ARCHITECTURE.md).

Production VPS — `185.105.111.112`; на нём работают приложение и PostgreSQL. VPS `46.30.47.95` используется только как SSH/SOCKS relay к Telegram. Не предлагать запускать на legacy VPS workers или считать его резервным production. Каноническая инструкция по доступам и эксплуатации: [`VPS_RUNBOOK.md`](VPS_RUNBOOK.md).

Ozon warehouse inventory uses `/v1/product/info/stocks-by-warehouse/fbo` and `/v2/product/info/stocks-by-warehouse/fbs`. Current rows are stored in `ozon_warehouse_stocks`, warehouse metadata in `ozon_warehouses`, and daily rows in `ozon_warehouse_stock_snapshots`. The legacy-compatible aggregate remains in `ozon_stocks` and `ozon_stock_snapshots`. Since 2026-08-17 Ozon stock analytics are realtime; `00:00 Europe/Moscow` is the application's business cutoff.

Доступные Ozon jobs: `products`, `orders`, `supplies`, `communications`,
`daily_sales`, `finances`, `documents`, `ads`. `documents` включается только после
ручного формирования первых асинхронных отчётов. На текущем VPS до развёртывания
этого изменения включены `products`, `orders`, `supplies`, `daily_sales`, `finances`
и `ads`; `documents` ещё требует миграции и первого запуска, а `communications`
выключен, потому что Reviews API кабинета возвращает HTTP 403. Активные задания запускаются независимо, используют
PostgreSQL advisory lock для защиты от пересечения и записывают результат в
`ozon_sync_runs`. Бизнес-дата Ozon рассчитывается в `OZON_TIMEZONE`, по умолчанию
`Europe/Moscow`.

Составные задачи могут завершиться статусом `partial`, если результат содержит
`*_error`; CLI в этом случае возвращает код `1`. Не считать такую запись успешной.

## Ключевые ограничения

- не выводить значения `.env`, токены или авторизационные заголовки;
- не придумывать поля API: моделировать по реальным ответам WB;
- сохранять идемпотентность повторных синхронизаций;
- не смешивать транспорт, бизнес-логику и persistence;
- использовать timezone-aware даты для нового кода;
- не менять унаследованный код без явной необходимости;
- после изменения импортов проверять точки запуска: `python -m wb --help`, `python -m telegram_bot --help`, `python -m ozon --help`, `python -m inventory_sync --help` и `python -m healthcheck`.
- worker документов запускать отдельно через `python -m wb.document_sync`; не встраивать его в постоянный WB-цикл или inventory workers.
- документы Ozon являются отдельным task `python -m ozon --task documents`; не смешивать его с начислениями `finances`.
- `operations_bot` не импортировать и не вызывать из marketplace workers: Telegram не должен влиять на их транзакции или exit code.
- не восстанавливать удалённый `mantra_sync`: он не относится к рабочей архитектуре.

## Проверки перед завершением изменений

```powershell
python -m pytest -q
python -m alembic heads
python -m wb.document_sync --help
```

Дополнительная документация: [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md), [`VPS_RUNBOOK.md`](VPS_RUNBOOK.md), [`../wb/README.md`](../wb/README.md), [`../wb/DOCUMENTS.md`](../wb/DOCUMENTS.md), [`../ozon/README.md`](../ozon/README.md), [`../ozon/ACCOUNTING.md`](../ozon/ACCOUNTING.md), [`../inventory_sync/README.md`](../inventory_sync/README.md), [`../telegram_bot/README.md`](../telegram_bot/README.md).
