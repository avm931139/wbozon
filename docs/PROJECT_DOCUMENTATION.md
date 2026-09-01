# Документация проекта wbozon

## Назначение

Проект синхронизирует данные кабинетов Wildberries, Ozon и Яндекс Маркета с PostgreSQL, отправляет управленческие и складские отчёты в Telegram, ведёт личный журнал выполненных действий и контролирует здоровье серверных процессов. Рабочая архитектура находится в пакетах `app`, `wb`, `ozon`, `yandex_market`, `inventory_sync`, `telegram_bot`, `operations_bot` и `healthcheck`. Каталог `legacy_core` сохранён как унаследованный каркас и не является частью основного процесса.

## Актуальная структура

- [`main.py`](../main.py) — совместимый alias отдельного WB worker;
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — каноническая схема независимых процессов и границ отказов;
- [`app/README.md`](../app/README.md) — общая конфигурация, БД и правила изменения моделей;
- [`app/config.py`](../app/config.py) — загрузка настроек из окружения и `.env`;
- [`app/db.py`](../app/db.py) — SQLAlchemy engine и фабрика сессий;
- [`app/models.py`](../app/models.py) — модели каталога, остатков, заказов, финансов, рекламы, обращений, журналов и доставок Telegram;
- [`wb/`](../wb) — API-клиенты, сервисы, репозитории, периодическая синхронизация WB и отдельная задача документов/баланса;
- [`ozon/`](../ozon) — каталог, остатки, отправления, поставки, обращения, продажи, документы и бухгалтерия Ozon Seller API, а также реклама Ozon Performance API;
- [`yandex_market/`](../yandex_market) — клиент Partner API и нормализация складских остатков;
- [`inventory_sync/`](../inventory_sync) — отдельные workers текущих остатков WB/Ozon/Яндекс Маркета и ежедневных срезов на 00:00 по Москве;
- [`telegram_bot/`](../telegram_bot) — формирование, планирование и отправка отчётов;
- [`operations_bot/`](../operations_bot) — личный дайджест успешных и ошибочных действий из журналов PostgreSQL;
- [`healthcheck/`](../healthcheck) — проверка systemd, свежести данных, полноты срезов и доставки Telegram;
- [`alembic/`](../alembic) — миграции PostgreSQL;
- [`tests/`](../tests) — модульные тесты;
- [`deploy/systemd/`](../deploy/systemd) — units постоянных workers и независимые timers;
- [`logs/wb/`](../logs/wb) — рабочие журналы синхронизации.

Подробности интеграции WB находятся в [`wb/README.md`](../wb/README.md), а документов и бухгалтерии — в [`wb/DOCUMENTS.md`](../wb/DOCUMENTS.md). Ozon описан в [`ozon/README.md`](../ozon/README.md), его документы и бухгалтерия — в [`ozon/ACCOUNTING.md`](../ozon/ACCOUNTING.md), сверка FBO-поставок — в [`ozon/SUPPLY_RECONCILIATION.md`](../ozon/SUPPLY_RECONCILIATION.md), периодические остатки — в [`inventory_sync/README.md`](../inventory_sync/README.md), групповые отчёты — в [`telegram_bot/README.md`](../telegram_bot/README.md), личный журнал — в [`operations_bot/README.md`](../operations_bot/README.md).

## Поток данных

```text
WB API → wb worker / WB documents / inventory@wb ────────────────┐
Ozon API → ozon tasks / inventory@ozon ─────────────────────────┤→ PostgreSQL
Яндекс Маркет API → inventory@yandex_market ────────────────────┤
                                                                 ├→ telegram workers → Telegram-группа
                                                                 ├→ operations_bot → личный Telegram
                                                                 └→ healthcheck → Telegram-группа
```

Telegram-модуль не запрашивает данные маркетплейсов напрямую. Он строит отчёты только по уже синхронизированной базе.

## Конфигурация

Создайте `.env` по образцу [`.env.example`](../.env.example). Секреты нельзя добавлять в Git, исходный код и документацию.

Обязательные настройки основного процесса:

- `DATABASE_URL` — URL PostgreSQL для SQLAlchemy;
- `WB_API_KEY` — токен Wildberries.

Для Telegram дополнительно нужны:

- `WB_TG_BOT_TOKEN` — токен BotFather;
- `WB_TG_CHAT_ID` — ID целевой группы, обычно отрицательное число.

Для личного журнала задайте `OPERATIONS_TG_CHAT_ID` — числовой ID личного диалога. Бот должен заранее получить от пользователя `/start`. По умолчанию модуль повторно использует `WB_TG_BOT_TOKEN` и `WB_TG_PROXY_URL`; при необходимости их можно переопределить через `OPERATIONS_TG_BOT_TOKEN` и `OPERATIONS_TG_PROXY_URL`.

Для Ozon нужны `OZON_CLIENT_ID` и `OZON_API_KEY`.

Все дополнительные URL, интервалы, таймауты, настройки логов и отчётов перечислены с комментариями в [`.env.example`](../.env.example).

## Установка и база данных

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Alembic является основным способом создания и обновления схемы. `python -m app.main` вызывает `Base.metadata.create_all()` и подходит только для простого локального создания отсутствующих таблиц, но не заменяет миграции.

### Обновление на VPS

Production работает на `185.105.111.112` под пользователем `wbozon`; `46.30.47.95` используется только как SSH/SOCKS relay для Telegram. Правила подключения, назначение ключей, Git-доступ, PostgreSQL, сетевые порты и аварийные сценарии собраны в [`VPS_RUNBOOK.md`](VPS_RUNBOOK.md).

Перед запуском нового кода всегда применяйте миграции, затем выполните контрольное обновление остатков и перезапустите постоянный сервис:

```bash
cd ~/wbozon
git pull --ff-only origin master
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m inventory_sync --marketplace wb --once
./.venv/bin/python -m inventory_sync --marketplace ozon --once
./.venv/bin/python -m inventory_sync --marketplace yandex_market --once
sudo systemctl restart 'wbozon-inventory@*.service'
sudo systemctl enable --now wbozon-operations.timer
systemctl --no-pager status 'wbozon-inventory@*.service'
```

Если `git status --short` показывает локальные изменения, сначала разберите их; принудительный сброс рабочей копии в процедуру обновления не входит.

На рабочем VPS используются отдельные `wbozon-inventory@wb.service`, `wbozon-inventory@ozon.service` и `wbozon-inventory@yandex_market.service`. Excel-отчёты запускает `wbozon-telegram-stock.timer` в 09:00 МСК. Старый общий inventory unit и cron-задание после миграции отключаются.

Healthcheck запускается каждые пять минут через `wbozon-healthcheck.timer`; определения unit-файлов и команды управления приведены в [`healthcheck/README.md`](../healthcheck/README.md).

## Запуск

Независимые постоянные workers:

```powershell
python -m wb
python -m wb.document_sync  # документы, локальные файлы и баланс WB
python -m telegram_bot
python -m inventory_sync --marketplace wb
python -m inventory_sync --marketplace ozon
python -m inventory_sync --marketplace yandex_market
python -m operations_bot      # один личный дайджест новых событий
```

Другие режимы:

```powershell
python -m wb --once         # один полный цикл WB
python main.py --once       # совместимый alias предыдущей команды
python -m telegram_bot      # только расписание Telegram
python -m telegram_bot --once operational
python -m telegram_bot --once morning
python -m telegram_bot --once stock-files       # Excel WB/Ozon за текущий московский день
python -m telegram_bot --once stock-files --date 2026-08-19 --force
python -m ozon --once       # один цикл Ozon
python -m ozon              # постоянная синхронизация Ozon
python -m ozon --report-day 2026-08-08   # сохранённый дневной срез
python -m ozon --report-month 2026-08    # сумма сохранённых дневных строк
python -m ozon --sync-ads                # только Ozon Performance
python -m inventory_sync --marketplace wb --once
python -m inventory_sync --marketplace ozon --snapshot
python -m inventory_sync --marketplace yandex_market --once
python -m healthcheck                    # сервисы, свежесть данных, срезы и Telegram
```

### Независимые задания Ozon

В production Ozon разделён на задания `products`, `orders`, `supplies`,
`supply_reconciliation`, `communications`, `daily_sales`, `finances`, `documents`,
`ads`. Каждый запуск записывается в
`ozon_sync_runs`, а повторный параллельный запуск того же задания блокируется
PostgreSQL advisory lock. Остатки остаются в отдельном `inventory_sync`.

На текущем VPS включены `products`, `orders`, `supplies`, `daily_sales`,
`finances` и `ads`. Новый `documents` включается после миграции и успешного ручного
запуска. `communications` доступен для ручной диагностики, но его timer
выключен: Questions API работает, Reviews API текущего кабинета отвечает HTTP 403.
Частичный результат с ключом `*_error` получает статус `partial` и ненулевой код
возврата.

```bash
.venv/bin/python -m ozon --task orders
.venv/bin/python -m ozon --task documents
.venv/bin/python -m ozon --task supply_reconciliation
```

Установка всех systemd units после `git pull` выполняется по инструкции [`deploy/systemd/README.md`](../deploy/systemd/README.md). Для Ozon отдельно включается рабочий набор timers:

```bash
.venv/bin/python -m alembic upgrade head
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  wbozon-ozon-products.timer \
  wbozon-ozon-orders.timer \
  wbozon-ozon-supplies.timer \
  wbozon-ozon-daily-sales.timer \
  wbozon-ozon-finances.timer \
  wbozon-ozon-ads.timer
```

Рекламный timer включается только при заполненных
`OZON_PERFORMANCE_CLIENT_ID` и `OZON_PERFORMANCE_CLIENT_SECRET`. Если реклама не
настроена, исключите `ads` из предыдущей команды и из `OZON_REQUIRED_TASKS`.

`communications` можно включить после успешного ручного запуска без
`reviews_error`:

```bash
sudo systemctl start wbozon-ozon@communications.service
sudo journalctl -u wbozon-ozon@communications.service -n 50 --no-pager
sudo systemctl enable --now wbozon-ozon-communications.timer
```

`documents` сначала запускается вручную. Первый запуск создаёт асинхронные
месячные отчёты; готовые файлы могут появиться только при следующем запуске:

```bash
./.venv/bin/python -m ozon --task documents
sudo systemctl enable --now wbozon-ozon-documents.timer
sudo systemctl start wbozon-ozon@documents.service
sudo journalctl -u wbozon-ozon@documents.service -n 100 --no-pager
```

Перед включением проверок healthcheck выполните каждое обязательное задание хотя
бы один раз, затем добавьте в `.env`:

```dotenv
OZON_TIMEZONE=Europe/Moscow
OZON_REQUIRED_TASKS=products,orders,supplies,daily_sales,finances,documents,ads
```

```bash
systemctl list-timers 'wbozon-ozon-*' --all
sudo systemctl start wbozon-ozon@orders.service
sudo journalctl -u wbozon-ozon@orders.service -n 100 --no-pager
```

Расписания задаются в `Europe/Moscow`; systemd показывает поле `NEXT` в локальной
временной зоне VPS. Полная инструкция находится в
[`deploy/systemd/README.md`](../deploy/systemd/README.md).

Отсутствие Telegram-настроек не влияет на WB/Ozon/inventory workers, потому что Telegram работает отдельным процессом. Повторная отправка уже доставленного ручного отчёта выполняется с флагом `--force`.

`operations_bot` также изолирован от рабочих процессов. Он читает только завершённые записи `wb_sync_runs`, `wb_document_sync_runs`, `ozon_sync_runs`, `inventory_sync_runs` и `wb_telegram_deliveries`. Новые события сначала фиксируются в `operations_event_deliveries`, поэтому при недоступном Telegram они не теряются и повторяются следующим запуском. Курсор `operations_monitor_states` исключает повторное чтение, а уникальный ключ события защищает от дублей.

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

Документы и баланс WB обновляет отдельный ежедневный `wbozon-wb-documents.timer`.
Он сохраняет справочник категорий, метаданные, один локальный файл на каждый
доступный формат документа, снимок баланса и общий результат в
`wb_document_sync_runs`. Его этапы выполняются независимо: ошибка Finance API не
откатывает уже сохранённые категории и документы. Подробнее — в
[`wb/DOCUMENTS.md`](../wb/DOCUMENTS.md).

Ozon в production запускается набором независимых tasks: товары, отправления FBS/FBO, поставки, обращения, дневные продажи, начисления, документы/бухгалтерия и реклама. Для рекламы используются отдельные учётные данные Ozon Performance API. Ozon не включён в WB worker, а дневные срезы его остатков являются источником отдельного Excel-отчёта Telegram.

Задание Ozon `documents` создаёт отсутствующие асинхронные месячные отчёты,
проверяет их готовность, скачивает файлы и сохраняет бухгалтерские JSON-снимки.
Запросы, статусы, файлы и снимки разделены между таблицами
`ozon_accounting_report_requests`, `ozon_accounting_reports`,
`ozon_accounting_report_files` и `ozon_accounting_snapshots`. Файлы находятся в
`data/ozon/accounting/` и резервируются отдельно от PostgreSQL. Ошибка отдельного
этапа даёт статус `partial`, не откатывая уже сохранённые этапы. Подробнее — в
[`ozon/ACCOUNTING.md`](../ozon/ACCOUNTING.md).

Ежедневный task `supply_reconciliation` получает заявленный состав отправленных
FBO-поставок, сводки актов и фактические строки приёмки по SKU. Нормализованные
таблицы объединяются SQL-представлением `ozon_fbo_supply_reconciliation`, где
доступны `sent_quantity`, `accepted_quantity` и `quantity_difference`, а брак,
излишки и недостачи остаются отдельными показателями. Timer запускается в 03:20
МСК. Подробнее — в
[`ozon/SUPPLY_RECONCILIATION.md`](../ozon/SUPPLY_RECONCILIATION.md).

Остатки загружают три постоянно работающих процесса `inventory_sync`, по одному на WB, Ozon и Яндекс Маркет. Текущие таблицы обновляются каждый час, исчезнувшие позиции обнуляются. В 00:00 `Europe/Moscow` каждый worker создаёт собственный идемпотентный срез и после простоя догоняет отсутствующую дату. Неудачный срез повторяется каждые `INVENTORY_SNAPSHOT_RETRY_SECONDS`. Ответы одного маркетплейса загружаются и фиксируются одной транзакцией; отказ другого API не вызывает откат. Запуски разделяются полем `inventory_sync_runs.marketplace` и разными advisory locks.

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
- в 09:00 МСК `wbozon-telegram-stock.timer` вызывает `python -m telegram_bot --once stock-files` и отправляет три `.xlsx` по срезу на 00:00 текущей московской даты;
- WB-файл содержит FBS/FBO, Ozon-файл — агрегат и детализацию по складам с их названиями и кластерами;
- нулевые остатки исключаются из Excel, а сами файлы создаются в памяти без временных файлов на диске;
- при отсутствии среза бот отправляет дедуплицированное предупреждение и продолжает отправку доступного маркетплейса.

Отдельный `wbozon-operations.timer` каждые пять минут отправляет в личный чат компактный журнал действий: успешные циклы WB, синхронизацию документов и баланса WB, независимые задания Ozon, обновления и срезы остатков каждого маркетплейса, успешные или ошибочные Telegram-доставки, новые ошибки healthcheck и последующее восстановление. Неизменный набор healthcheck-ошибок повторно не отправляется. Для ошибок добавляется сохранённая причина, вероятное объяснение и команда журнала соответствующего systemd unit. Успешные события можно отключить через `OPERATIONS_TG_INCLUDE_SUCCESSES=false`.

## Журналы и диагностика

Основной журнал WB-процесса: `logs/wb/wb_sync.log`; Telegram использует отдельный каталог `logs/telegram/`. Ozon, inventory и healthcheck пишут в journal systemd, а результаты прикладных запусков дополнительно сохраняются в `ozon_sync_runs` и `inventory_sync_runs`. Процессы не ротируют один файл одновременно.

`python -m healthcheck` проверяет отдельные systemd workers, свежесть inventory по каждому маркетплейсу, обязательные Ozon jobs, пять таблиц срезов, доставку трёх складских файлов после 09:30, активность личного timer, свежесть его курсора и ошибки очереди. Команда возвращает `0` при норме и `1` при ошибках. Новый набор ошибок один раз отправляется в Telegram; повтор одинакового набора подавляется, а после восстановления отправляется отдельное сообщение. На VPS команда запускается парой `wbozon-healthcheck.service` (`Type=oneshot`) и `wbozon-healthcheck.timer` каждые пять минут.

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
