# wbozon

Проект на Python для синхронизации данных Wildberries, Ozon и Яндекс Маркета с PostgreSQL, формирования Telegram-отчётов и контроля здоровья серверных процессов.

## Обзор

Проект сочетает в себе:

- базовый application layer в пакете app;
- ORM-модели и инициализацию базы данных на SQLAlchemy;
- переиспользуемый слой интеграции с Wildberries в пакете wb;
- отдельный worker документов, локальных файлов и баланса Wildberries;
- отдельное Ozon-задание документов, бухгалтерских JSON-отчётов и локальных файлов;
- ежедневная сверка отправленного и фактически принятого количества FBO Ozon по SKU;
- отдельный корневой пакет Telegram-отчётов `telegram_bot`;
- проверку сервисов, свежести данных и доставки отчётов в пакете `healthcheck`;
- личный операционный дайджест успешных и ошибочных действий в пакете `operations_bot`;
- отдельный интеграционный пакет Ozon Seller API `ozon`;
- отдельный интеграционный пакет Partner API Яндекс Маркета `yandex_market`;
- независимые по маркетплейсам workers текущих остатков и ежедневных срезов `inventory_sync`, включая детализацию Ozon по физическим складам;
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
  - `__main__.py` — отдельная точка запуска `python -m wb`.
  - `document_sync.py` — независимая задача `python -m wb.document_sync`.
- telegram_bot/
  - client.py — клиент Telegram Bot API.
  - reports.py — формирование дневных и месячных отчётов.
  - scheduler.py — расписание отправки.
  - dispatcher.py — доставка и защита от дублей.
  - stock_reports.py — Excel-отчёты дневных остатков WB/Ozon/Яндекс Маркета в памяти.
- ozon/
  - client.py — клиент Ozon Seller API.
  - API-модули — каталог, агрегатные и складские остатки, отправления, поставки, обращения, аналитика и финансы.
  - `warehouse_stocks.py` — остатки Ozon FBO/FBS по физическим складам и метаданные складов.
  - performance/ — отдельный клиент и сервис Ozon Performance API.
  - services/ и repositories/ — синхронизация, нормализация и сохранение данных.
  - scheduler.py — отдельное расписание Ozon.
- yandex_market/
  - client.py — авторизация, повторы и обработка ошибок Partner API.
  - stocks.py — получение полных остатков кампаний с пагинацией.
- inventory_sync/
  - service.py — изолированная по маркетплейсам загрузка и атомарное сохранение остатков.
  - scheduler.py — почасовое обновление и срез в 00:00 по Москве.
  - `__main__.py` — команда `python -m inventory_sync`.
- healthcheck/
  - `__main__.py` — проверка systemd, БД, дневных срезов и Telegram.
- operations_bot/
  - service.py — чтение журналов БД, очередь событий и личный Telegram-дайджест.
  - `__main__.py` — разовый запуск `python -m operations_bot`.
- deploy/systemd/
  - units всех постоянных workers и независимые timers.
- legacy_core/
  - архивный пустой пакет, не участвующий в рабочем процессе.
- main.py — совместимый alias для отдельного WB worker; Telegram он не запускает.
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
- openpyxl
- Alembic

## Конфигурация

Все настройки читаются из переменных окружения или локального .env.

### Обязательные переменные

- DATABASE_URL — строка подключения к PostgreSQL.
- WB_API_KEY — API-ключ Wildberries.

### Telegram-отчёты

- `WB_TG_BOT_TOKEN` — токен бота от BotFather.
- `WB_TG_CHAT_ID` — ID группы для отчётов.

Для личного технического журнала задайте `OPERATIONS_TG_CHAT_ID`. По умолчанию он использует тот же bot token и proxy, но отправляет сообщения в отдельный личный чат.

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

## Независимый запуск процессов

Wildberries и Telegram имеют разные точки запуска:

```bash
python -m wb
python -m telegram_bot
```

Однократные проверки:

```bash
python -m wb --once
python -m wb.document_sync
python -m telegram_bot --once operational
python -m operations_bot
```

`python main.py` оставлен как alias для `python -m wb`; совместного WB+Telegram процесса больше нет.

Ozon поддерживает общий диагностический цикл и независимые production-задания:

```bash
python -m ozon --once
python -m ozon --task products
python -m ozon --task orders
python -m ozon --task supplies
python -m ozon --task supply_reconciliation
python -m ozon --task communications
python -m ozon --task daily_sales
python -m ozon --task finances
python -m ozon --task documents
python -m ozon --task ads
python -m ozon --report-day 2026-08-08
python -m ozon --report-month 2026-08
python -m ozon --sync-ads
```

Каждое задание защищено от параллельного запуска и записывает статус в
`ozon_sync_runs`. Production-расписания находятся в `deploy/systemd`.
На текущем VPS включены `products`, `orders`, `supplies`, `daily_sales`, `finances`
и `ads`. Задание `documents` включается после миграции и первого ручного запуска.
Ежедневное задание `supply_reconciliation` также включается после миграции и
первого исторического запуска.
Задание `communications` доступно вручную, но не включено из-за HTTP 403 от Ozon
Reviews API текущего кабинета.

Остатки запускаются тремя независимыми процессами:

```bash
python -m inventory_sync --marketplace wb
python -m inventory_sync --marketplace ozon
python -m inventory_sync --marketplace yandex_market
```

По умолчанию текущие остатки обновляются каждый час, а ежедневный срез создаётся в 00:00 `Europe/Moscow` независимо от часового пояса сервера.

Если обязательный этап дневного среза завершился ошибкой, соответствующий worker повторяет его каждые 300 секунд. Остальные маркетплейсы продолжают работу.

С 17 августа 2026 года Ozon возвращает остатки в реальном времени, поэтому 00:00 МСК является бизнес-временем среза проекта. Агрегаты Ozon сохраняются в `ozon_stocks`, детализация — в `ozon_warehouse_stocks`, справочник складов — в `ozon_warehouses`. Ежедневная складская история записывается в `ozon_warehouse_stock_snapshots`.

Каждая команда `python -m inventory_sync --marketplace ...` работает постоянно отдельным процессом. Запуски сохраняются в `inventory_sync_runs` вместе с полем `marketplace`; при ошибке API частичный срез только этого маркетплейса не записывается.

Ежедневная отправка трёх Excel-файлов по срезу текущей московской даты:

```bash
python -m telegram_bot --once stock-files
```

## Архитектурные принципы

1. HTTP-инфраструктура должна быть централизована.
2. Endpoint-пути должны храниться в одном месте.
3. API-модули должны быть узкоспециализированными.
4. Логика нормализации и бизнес-правила — в сервисах.
5. Работа с базой данных — в репозиториях.
6. Production-процессы не запускают друг друга и обмениваются состоянием только через PostgreSQL.
7. Операционные уведомления читают журналы асинхронно и никогда не меняют результат marketplace worker.

Точная схема процессов, границы отказов и общие зависимости описаны в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Проект является модульным монолитом с независимыми workers, а не набором автономно развертываемых сетевых микросервисов.

## Дополнительная документация

Полный индекс находится в [docs/README.md](docs/README.md). Подробное описание проекта доступно в [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md), инструкция по production и двум VPS — в [docs/VPS_RUNBOOK.md](docs/VPS_RUNBOOK.md), общей инфраструктуры — в [app/README.md](app/README.md), интеграции WB — в [wb/README.md](wb/README.md), документов WB — в [wb/DOCUMENTS.md](wb/DOCUMENTS.md), Ozon — в [ozon/README.md](ozon/README.md), документов Ozon — в [ozon/ACCOUNTING.md](ozon/ACCOUNTING.md), сверки FBO-поставок — в [ozon/SUPPLY_RECONCILIATION.md](ozon/SUPPLY_RECONCILIATION.md), остатков — в [inventory_sync/README.md](inventory_sync/README.md), групповых отчётов — в [telegram_bot/README.md](telegram_bot/README.md), личного журнала — в [operations_bot/README.md](operations_bot/README.md), мониторинга — в [healthcheck/README.md](healthcheck/README.md), systemd-задач — в [deploy/systemd/README.md](deploy/systemd/README.md).

Проверка работающих сервисов, свежести данных, полноты дневных срезов и доставки Telegram:

```bash
python -m healthcheck
```

Команда возвращает код `0`, если все проверки успешны, и `1`, если обнаружена проблема. Новый набор ошибок один раз отправляется в настроенную Telegram-группу; одинаковые ошибки не дублируются при каждом запуске. После устранения проблем бот отправляет сообщение о восстановлении.
