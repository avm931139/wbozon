# Контекст проекта для AI-ассистентов

## Цель

`wbozon` — рабочее приложение для загрузки данных Wildberries и Ozon в PostgreSQL и отправки аналитических отчётов в Telegram.

## Актуальная архитектура

- `app/` — конфигурация, подключение к БД и ORM-модели;
- `wb/` — основной интеграционный слой Wildberries;
- `ozon/` — интеграционный слой Ozon Seller/Performance API для каталога, логистики, обращений, продаж, финансов и рекламы;
- `inventory_sync/` — отдельный процесс текущих остатков WB/Ozon и ежедневных срезов в 01:00 `Europe/Moscow`;
- `telegram_bot/` — корневой пакет Telegram-отчётов;
- `main.py` — совместный запуск синхронизации WB и Telegram-отчётов; Ozon запускается отдельно через `python -m ozon`;
- `alembic/` — единственный основной механизм эволюции схемы;
- `tests/` — актуальные тесты новой архитектуры.

Папка `legacy_core/` является унаследованной/справочной. Не следует подключать её к основному процессу или переносить из неё код без отдельного решения о миграции.

## Поток данных

```text
WB API → wb API class → service → repository/session → app.models → PostgreSQL
Ozon API → ozon API class → service → repository/session → app.models → PostgreSQL
WB/Ozon stock APIs → inventory_sync → current stocks + daily snapshot tables
Telegram API ← telegram_bot ← PostgreSQL
```

## Ключевые ограничения

- не выводить значения `.env`, токены или авторизационные заголовки;
- не придумывать поля API: моделировать по реальным ответам WB;
- сохранять идемпотентность повторных синхронизаций;
- не смешивать транспорт, бизнес-логику и persistence;
- использовать timezone-aware даты для нового кода;
- не менять унаследованный код без явной необходимости;
- после изменения импортов проверять точки запуска: `python main.py --help`, `python -m telegram_bot --help`, `python -m ozon --help` и `python -m inventory_sync --help`.

## Проверки перед завершением изменений

```powershell
python -m pytest -q
python -m alembic heads
```

Дополнительная документация: [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md), [`../wb/README.md`](../wb/README.md), [`../ozon/README.md`](../ozon/README.md), [`../inventory_sync/README.md`](../inventory_sync/README.md), [`../telegram_bot/README.md`](../telegram_bot/README.md).
