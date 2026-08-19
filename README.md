# wbozon

Проект на Python для синхронизации данных Wildberries и Ozon с PostgreSQL, а также для формирования Telegram-отчётов по кабинету Wildberries.

## Обзор

Проект сочетает в себе:

- базовый application layer в пакете app;
- ORM-модели и инициализацию базы данных на SQLAlchemy;
- переиспользуемый слой интеграции с Wildberries в пакете wb;
- отдельный корневой пакет Telegram-отчётов `telegram_bot`;
- отдельный интеграционный пакет Ozon Seller API `ozon`;
- независимый планировщик текущих остатков и ежедневных срезов `inventory_sync`, включая детализацию Ozon по физическим складам;
- миграции схемы PostgreSQL и автоматические тесты.

## Структура проекта

- app/
  - config.py — конфигурация окружения и переменные доступа.
  - db.py — engine, session factory и declarative base.
  - models.py — ORM-модели приложения.
  - main.py — точка инициализации базы данных.
- wb/
  - client.py — общий HTTP-клиент для WB API.
  - endpoints.py — централизованные endpoint-константы.
  - доменные API-модули — каталог, склады, остатки, заказы, поставки, финансы, обращения и реклама.
  - exceptions.py — пользовательские исключения.
  - services/ — слой бизнес-логики.
  - repositories/ — слой сохранения данных.
- telegram_bot/
  - client.py — клиент Telegram Bot API.
  - reports.py — формирование дневных и месячных отчётов.
  - scheduler.py — расписание отправки.
  - dispatcher.py — доставка и защита от дублей.
- ozon/
  - client.py — клиент Ozon Seller API.
- API-модули — каталог, агрегатные и складские остатки, отправления, поставки, обращения, аналитика и финансы.
  - `warehouse_stocks.py` — остатки Ozon FBO/FBS по физическим складам и метаданные складов.
  - performance/ — отдельный клиент и сервис Ozon Performance API.
  - services/ и repositories/ — синхронизация, нормализация и сохранение данных.
  - scheduler.py — отдельное расписание Ozon.
- inventory_sync/
  - service.py — полная загрузка и атомарное сохранение остатков WB/Ozon, включая Ozon по складам.
  - scheduler.py — почасовое обновление и срез в 01:00 по Москве.
  - `__main__.py` — команда `python -m inventory_sync`.
- main.py — совместный запуск синхронизации WB и Telegram-отчётов.
- docs/
  - PROJECT_DOCUMENTATION.md — подробная техническая документация проекта.
- tests/ — тесты.

## Требования

- Python 3.11+
- SQLAlchemy 2.x
- psycopg 3
- python-dotenv
- pytest
- requests
- Alembic

## Конфигурация

Все настройки читаются из переменных окружения или локального .env.

### Обязательные переменные

- DATABASE_URL — строка подключения к PostgreSQL.
- WB_API_KEY — API-ключ Wildberries.

### Telegram-отчёты

- `WB_TG_BOT_TOKEN` — токен бота от BotFather.
- `WB_TG_CHAT_ID` — ID группы для отчётов.

Остальные параметры и значения по умолчанию перечислены в [`.env.example`](.env.example).

### Ozon

- `OZON_CLIENT_ID` — идентификатор продавца;
- `OZON_API_KEY` — API-ключ Ozon Seller.

### Основные необязательные переменные

- WB_BASE_URL — базовый URL WB API, по умолчанию https://suppliers-api.wildberries.ru.
- WB_TIMEOUT_SECONDS — таймаут запросов, по умолчанию 30.

Пример:

```bash
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/wbozon
WB_API_KEY=your_wb_api_key
WB_BASE_URL=https://suppliers-api.wildberries.ru
WB_TIMEOUT_SECONDS=30
```

## Установка зависимостей

```bash
python -m pip install -r requirements.txt
```

## Обновление базы данных

```bash
python -m alembic upgrade head
```

Команда `python -m app.main` создаёт только отсутствующие таблицы и не заменяет миграции Alembic.

## Запуск тестов

```bash
python -m pytest
```

## Запуск синхронизации и Telegram-отчётов

После заполнения `WB_TG_BOT_TOKEN` и `WB_TG_CHAT_ID` оба расписания запускаются одной командой:

```bash
python main.py
```

Для запуска только синхронизации используйте `python main.py --sync-only`. Однократный полный цикл синхронизации запускается командой `python main.py --once`.

Telegram-модуль можно запустить отдельно:

```bash
python -m telegram_bot
python -m telegram_bot --once operational
```

Ozon пока запускается отдельным процессом:

```bash
python -m ozon --once
python -m ozon
python -m ozon --report-day 2026-08-08
python -m ozon --report-month 2026-08
python -m ozon --sync-ads
```

Остатки WB и Ozon запускаются третьим независимым процессом:

```bash
python -m inventory_sync
python -m inventory_sync --once
python -m inventory_sync --snapshot
```

По умолчанию текущие остатки обновляются каждый час, а ежедневный срез создаётся в 01:00 `Europe/Moscow` независимо от часового пояса сервера.

С 17 августа 2026 года Ozon возвращает остатки в реальном времени, поэтому 01:00 МСК является бизнес-временем среза проекта. Агрегаты Ozon сохраняются в `ozon_stocks`, детализация — в `ozon_warehouse_stocks`, справочник складов — в `ozon_warehouses`. Ежедневная складская история записывается в `ozon_warehouse_stock_snapshots`.

Команда `python -m inventory_sync` должна работать постоянно как отдельный процесс. Успешные и неуспешные запуски сохраняются в `inventory_sync_runs`; при ошибке обязательного API-этапа частичный ежедневный срез не записывается. В журнале отдельно фиксируется количество агрегатных строк Ozon и строк Ozon по складам.

## Архитектурные принципы

1. HTTP-инфраструктура должна быть централизована.
2. Endpoint-пути должны храниться в одном месте.
3. API-модули должны быть узкоспециализированными.
4. Логика нормализации и бизнес-правила — в сервисах.
5. Работа с базой данных — в репозиториях.

## Дополнительная документация

Подробное описание проекта доступно в [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md), интеграции WB — в [wb/README.md](wb/README.md), Ozon — в [ozon/README.md](ozon/README.md), остатков — в [inventory_sync/README.md](inventory_sync/README.md), отчётов — в [telegram_bot/README.md](telegram_bot/README.md).
