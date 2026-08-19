# Документация проекта wbozon

## Назначение

Проект синхронизирует данные кабинетов Wildberries и Ozon с PostgreSQL и отправляет управленческие отчёты WB в Telegram. Рабочая архитектура находится в пакетах `app`, `wb`, `ozon`, `inventory_sync` и `telegram_bot`. Каталог `legacy_core` сохранён как унаследованный каркас и не является частью основного процесса.

## Актуальная структура

- [`main.py`](../main.py) — единая точка запуска синхронизации и Telegram-отчётов;
- [`app/config.py`](../app/config.py) — загрузка настроек из окружения и `.env`;
- [`app/db.py`](../app/db.py) — SQLAlchemy engine и фабрика сессий;
- [`app/models.py`](../app/models.py) — модели каталога, остатков, заказов, финансов, рекламы, обращений, журналов и доставок Telegram;
- [`wb/`](../wb) — API-клиенты, сервисы, репозитории и периодическая синхронизация WB;
- [`ozon/`](../ozon) — каталог, остатки, отправления, поставки, обращения, продажи и финансы Ozon Seller API, а также реклама Ozon Performance API;
- [`inventory_sync/`](../inventory_sync) — отдельное расписание текущих остатков WB/Ozon, детализации Ozon по складам и ежедневных срезов на 00:00 по Москве;
- [`telegram_bot/`](../telegram_bot) — формирование, планирование и отправка отчётов;
- [`alembic/`](../alembic) — миграции PostgreSQL;
- [`tests/`](../tests) — модульные тесты;
- [`logs/wb/`](../logs/wb) — рабочие журналы синхронизации.

Подробности интеграции WB находятся в [`wb/README.md`](../wb/README.md), Ozon — в [`ozon/README.md`](../ozon/README.md), периодических остатков — в [`inventory_sync/README.md`](../inventory_sync/README.md), отчётов — в [`telegram_bot/README.md`](../telegram_bot/README.md).

## Поток данных

```text
WB API → API-модули wb → сервисы → репозитории/SQLAlchemy → PostgreSQL
                                                                  ↓
                                                telegram_bot → Telegram API
Ozon API → API-модули ozon → сервисы → репозитории/SQLAlchemy ┘
Ozon warehouse APIs → inventory_sync → текущие строки и дневные срезы по физическим складам
```

Telegram-модуль не запрашивает данные WB напрямую. Он строит отчёты только по уже синхронизированной базе.

## Конфигурация

Создайте `.env` по образцу [`.env.example`](../.env.example). Секреты нельзя добавлять в Git, исходный код и документацию.

Обязательные настройки основного процесса:

- `DATABASE_URL` — URL PostgreSQL для SQLAlchemy;
- `WB_API_KEY` — токен Wildberries.

Для Telegram дополнительно нужны:

- `WB_TG_BOT_TOKEN` — токен BotFather;
- `WB_TG_CHAT_ID` — ID целевой группы, обычно отрицательное число.

Для Ozon нужны `OZON_CLIENT_ID` и `OZON_API_KEY`.

Все дополнительные URL, интервалы, таймауты, настройки логов и отчётов перечислены с комментариями в [`.env.example`](../.env.example).

## Установка и база данных

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Alembic является основным способом создания и обновления схемы. `python -m app.main` вызывает `Base.metadata.create_all()` и подходит только для простого локального создания отсутствующих таблиц, но не заменяет миграции.

### Обновление на VPS

Перед запуском нового кода всегда применяйте миграции, затем выполните контрольное обновление остатков и перезапустите постоянный сервис:

```bash
cd ~/wbozon
git pull --ff-only origin master
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m inventory_sync --once
sudo systemctl restart wbozon-inventory.service
sudo systemctl status wbozon-inventory.service --no-pager
```

Если `git status --short` показывает локальные изменения, сначала разберите их; принудительный сброс рабочей копии в процедуру обновления не входит.

## Запуск

Синхронизация и Telegram-отчёты вместе:

```powershell
python main.py
```

Другие режимы:

```powershell
python main.py --once       # один полный цикл синхронизации
python main.py --sync-only  # постоянная синхронизация без Telegram
python -m telegram_bot      # только расписание Telegram
python -m telegram_bot --once operational
python -m telegram_bot --once morning
python -m ozon --once       # один цикл Ozon
python -m ozon              # постоянная синхронизация Ozon
python -m ozon --report-day 2026-08-08   # сохранённый дневной срез
python -m ozon --report-month 2026-08    # сумма сохранённых дневных строк
python -m ozon --sync-ads                # только Ozon Performance
python -m inventory_sync                 # почасовые остатки и срез в 00:00 МСК
python -m inventory_sync --once          # разовое обновление текущих остатков
python -m inventory_sync --snapshot      # ручной срез за московскую дату
```

Если Telegram-настройки отсутствуют, `main.py` продолжает синхронизацию и пишет предупреждение в журнал. Повторная отправка уже доставленного ручного отчёта выполняется с флагом `--force`.

## Синхронизируемые разделы

Периодический цикл последовательно обновляет:

1. категории и карточки товаров;
2. склады FBS;
3. заказы и операционные продажи;
4. поставки FBW;
5. финансовые отчёты продаж и эквайринга;
6. вопросы и отзывы;
7. кампании и статистику рекламы.

Ошибка одной задачи записывается в журнал и не блокирует выполнение следующих независимых задач.

Ozon отдельным процессом последовательно синхронизирует товары, отправления FBS/FBO, поставки, обращения, дневные продажи, финансы и рекламу. Для рекламы используются отдельные учётные данные Ozon Performance API. Ошибка одного раздела не останавливает остальные задачи цикла. Ozon пока не включён в корневой `main.py` и не является источником Telegram-отчётов.

Остатки WB FBS, WB FBO и Ozon загружаются третьим постоянно работающим процессом `inventory_sync`. Текущие таблицы обновляются каждый час, исчезнувшие позиции обнуляются. В 00:00 `Europe/Moscow` создаются идемпотентные срезы в `wb_fbs_stock_snapshots`, `wb_fbo_stock_snapshots`, `ozon_stock_snapshots` и `ozon_warehouse_stock_snapshots`; после простоя отсутствующий срез догоняется при запуске. Обязательные ответы API сначала полностью загружаются в память и проверяются, затем текущие значения и срез фиксируются одной транзакцией. Неуспешные и успешные попытки записываются в `inventory_sync_runs`.

Ozon хранится в двух представлениях:

- `ozon_stocks` и `ozon_stock_snapshots` — совместимый агрегат по `product_id + stock_type`;
- `ozon_warehouses` — справочник физических складов Ozon;
- `ozon_warehouse_stocks` — текущие FBO/FBS-остатки по `product_id + warehouse_id + stock_type`;
- `ozon_warehouse_stock_snapshots` — ежедневная складская история.

Основные складские источники Ozon: `/v1/product/info/stocks-by-warehouse/fbo` и `/v2/product/info/stocks-by-warehouse/fbs`. `/v1/analytics/stocks` используется для названий складов и кластеров. С 17 августа 2026 года Ozon отдаёт аналитические остатки в реальном времени, поэтому `00:00 Europe/Moscow` — внутреннее бизнес-время фиксации, а не время публикации данных API.

Полная схема загрузки и правила сверки описаны в [`ozon/WAREHOUSE_STOCK_ARCHITECTURE.md`](../ozon/WAREHOUSE_STOCK_ARCHITECTURE.md).

## Telegram-отчёты

- утренний отчёт содержит прошлый день и текущий месяц по вчера включительно;
- оперативный отчёт показывает текущий день;
- дополнительно выводятся реклама, остатки, обращения и состояние синхронизации;
- таблица `wb_telegram_deliveries` хранит статусы и защищает от дублей после перезапуска.

## Журналы и диагностика

Основной журнал общего WB-процесса: `logs/wb/wb_sync.log`. Ошибки также сохраняются в БД и структурированном журнале согласно настройкам `WB_LOG_*`. Отдельный процесс остатков пишет стандартный поток логов процесса, а результат каждого запуска сохраняет в `inventory_sync_runs`.

Проверка состояния процесса начинается с последних строк журнала:

```powershell
Get-Content -Encoding UTF8 -Tail 100 .\logs\wb\wb_sync.log
```

## Тестирование

```powershell
python -m pytest -q
python -m alembic current
python -m alembic heads
```

Число тестов со временем меняется; критерием успешной проверки является отсутствие падений всего набора.

## Правила развития

1. HTTP-вызовы размещаются в доменных API-модулях `wb` и используют общий клиент.
2. Нормализация и бизнес-правила находятся в сервисах.
3. Повторяющиеся операции сохранения выносятся в репозитории.
4. Изменения схемы оформляются миграциями Alembic.
5. Синхронизация должна оставаться идемпотентной и безопасной для повторного запуска.
6. Новые возможности сопровождаются тестами и обновлением соответствующего README.
