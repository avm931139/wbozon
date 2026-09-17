# Технический аудит проекта wbozon

Дата аудита: 16.09.2026  
Роль ревьюера: senior-разработчик / архитектурный аудит  
Статус на момент первоначального аудита: кодовая база работоспособна на уровне
unit-тестов, но проверенное локальное окружение не готово к безопасному запуску
актуальной версии без устранения P0. Актуальный статус production приведён ниже.

## 0. Статус повторной проверки production

После аудита production-окружение на VPS было проверено отдельно от локальной
БД, указанной в окружении первоначального аудита.

- production Git revision после исправления: `ea5b20f`;
- `alembic current`: `20260911_wb_funnel_account (head)`;
- `alembic heads`: `20260911_wb_funnel_account (head)`;
- `alembic check`: `No new upgrade operations detected`;
- миграции и другие DDL-операции на production-БД не запускались.

P0-01 не относился к production-БД: первоначальный результат с ревизией
`20260819_ozon_wh_stocks` получен для другого окружения. В production все
миграции уже были применены. При повторной проверке был обнаружен не backlog
миграций, а drift ORM metadata: модели иначе описывали существующие unique
constraints/indexes и комментарии, а тип `yandex_market_sales_analytics_daily.id`
был ошибочно объявлен как `Integer` вместо существующего `BIGINT`. Метаданные
приведены в соответствие фактической схеме без перестройки таблиц.

Также исправлен запуск `alembic/env.py`: команды `.venv/bin/alembic ...` теперь
самостоятельно добавляют корень проекта в `sys.path` и загружают `.env` из
корня репозитория, поэтому ручной `PYTHONPATH=.` больше не требуется.

При проверке на VPS обычный `pytest` обнаружил обращение unit-теста остатков к
живому Yandex API из-за production-переменных окружения. Тест изолирован явным
пустым списком кампаний. По умолчанию `pytest` теперь исключает маркер
`integration`, а PostgreSQL-тест принимает только отдельный
`TEST_DATABASE_URL`, имя БД которого содержит `test`. Таким образом, обычный
тестовый запуск больше не обращается к production API или PostgreSQL.

## 1. Область и ограничения аудита

Проверены:

- 255 Python-файлов, около 28 748 строк Python-кода;
- пакеты `app`, `wb`, `ozon`, `yandex_market`, `inventory_sync`, `dashboard`, `telegram_bot`, `operations_bot`, `healthcheck`, `finance_reconciliation`, `price_sync`, `product_master`, `product_catalog`, `product_costs`, `supply_movement_report`;
- 40 файлов тестов;
- 45 файлов Alembic-миграций;
- systemd units/timers, Nginx-конфигурация и инструкции развёртывания;
- README и документация, включая `docs/dialog_history/2026-08-09_wb_cabinet_summary.md` и `docs/project_context_for_chatgpt.md`;
- история Git и текущее состояние рабочего дерева;
- схема БД, указанной в текущем `DATABASE_URL`, только read-only запросами к метаданным.

Полной выгрузки исходного чата в репозитории нет. Найден только краткий итог диалога от 09.08.2026, поэтому выводы о принятых ранее решениях основаны на коде, Git-истории и имеющейся документации.

Содержимое `.env`, временного cookie-файла и финансовых XLSX не просматривалось и в отчёт не выводится.

## 2. Выполненные проверки

| Проверка | Результат |
|---|---|
| `pytest -q` | 243 passed, 123 warnings |
| `compileall` рабочих пакетов | успешно |
| `pip check` | конфликтов установленных зависимостей нет |
| `alembic heads` | один head: `20260911_wb_funnel_account` |
| Полная генерация offline SQL Alembic | успешно |
| `alembic check` для текущей БД | ошибка: `Target database is not up to date` |
| Текущая ревизия БД | `20260819_ozon_wh_stocks` |
| Ожидающая цепочка миграций | 22 миграции |
| Таблицы в текущей БД / ORM-модели | 58 / 106 |

Важно: зелёный `pytest` не проверяет совместимость актуального кода с актуальной PostgreSQL-схемой. Единственный тест с маркером `integration` выполняет только `SELECT 1`.

## 3. Шкала приоритетов

- **P0 — блокирует безопасный запуск или обновление.** Исправлять до деплоя.
- **P1 — высокий риск потери/искажения данных, простоя или быстрого ухудшения производительности.** Исправлять в ближайший спринт.
- **P2 — существенный технический долг и эксплуатационный риск.** Планировать после P0/P1.
- **P3 — локальная проблема качества или документации.** Исправлять по мере работы с модулем.

## 4. Краткий итог

Сильная сторона проекта — явное разделение интеграций по доменам, идемпотентность многих загрузок, транзакционная замена остатков, advisory locks в новых workers, журналирование запусков и хорошая защита путей локального файлового хранилища. Для проекта такого возраста тестов уже много.

Главные узкие места:

1. код опережает схему текущей БД на 22 миграции;
2. отсутствует автоматический CI-контур, который обнаружил бы это до запуска;
3. ряд синхронизаций загружает целые растущие таблицы в память при каждом цикле;
4. нет реализованной политики retention/архивирования для истории, JSON и файлов;
5. Yandex Market частично поддерживает несколько business ID, но finance и advertising могут удалить или смешать данные другого бизнеса;
6. dashboard выполняет тяжёлые синхронные агрегации на каждый запрос и не имеет ограниченного пула HTTP workers;
7. резервное копирование описано только вручную и не подтверждается кодом/таймером проекта.

## 5. Найденные проблемы

### P0-01. Текущая БД отстаёт от кода на 22 миграции

**Доказательства**

- `alembic check` возвращает `Target database is not up to date`.
- Текущая ревизия: `20260819_ozon_wh_stocks`; head: `20260911_wb_funnel_account`.
- В БД 58 таблиц при 106 `__tablename__` в `app/models.py`.
- В текущей БД отсутствуют, в частности, `ozon_sync_runs`, `yandex_market_orders`, `marketplace_product_media`, `product_cost_records`, `wb_sales_funnel_account_daily`.

Это относится именно к БД из локального текущего `DATABASE_URL`. Без отдельной проверки нельзя автоматически считать её production или development.

**Риск**

Актуальные workers, healthcheck и dashboard будут падать на отсутствующих таблицах/колонках. Простое выполнение `alembic upgrade head` без предварительной репетиции опасно: цепочка длинная, содержит backfill, изменение ограничений, представление и операции очистки данных.

**Исправление**

1. Определить назначение текущей БД.
2. Создать согласованный `pg_dump -Fc` и отдельно сохранить файловые каталоги.
3. Восстановить дамп в отдельную тестовую БД.
4. Выполнить на копии `alembic upgrade head`, затем `alembic check`.
5. Прогнать PostgreSQL integration/smoke tests всех CLI и dashboard-запросов.
6. Только после успешной репетиции подготовить окно обновления целевой БД.

**Критерий готовности**

- `alembic current` совпадает с `alembic heads`;
- `alembic check` сообщает отсутствие новых upgrade operations;
- smoke tests выполняют реальные запросы ко всем таблицам актуальных workers.

### P1-01. Нет автоматизированного и проверяемого резервного копирования

**Статус 17.09.2026:** код и эксплуатационный контур реализованы: Restic,
ежедневный внешний зашифрованный snapshot, retention 7/5/12, repository check,
ежемесячное восстановление в отдельную БД, systemd timers и контроль через
healthcheck/operations bot. Риск считается закрытым только после настройки
внешнего назначения на production и первого успешного `run` + `verify`.

**Доказательства**

В `docs/VPS_RUNBOOK.md:350-368` приведён только ручной пример `pg_dump`; backup service/timer, шифрование, ротация, внешний upload и автоматическая проверка восстановления в `deploy/` отсутствуют. Кроме PostgreSQL существуют важные файлы в `data/wb/documents`, `data/ozon/accounting`, `data/product_media` и reconciliation-каталогах.

**Риск**

Единственный VPS остаётся точкой потери БД и файлов. Наличие локального дампа на том же сервере не является резервной копией. Перед P0-миграцией это особенно опасно.

**Исправление**

- добавить отдельные systemd service/timer для ежедневного backup;
- включить PostgreSQL, нужные `data/`-каталоги и зашифрованную копию конфигурации;
- выгружать результат во внешнее хранилище с retention, например 7 daily / 5 weekly / 12 monthly;
- ежедневно проверять целостность, ежемесячно восстанавливать в отдельную БД и выполнять smoke test;
- отправлять результат backup/restore-check в healthcheck/operations bot.

### P1-02. Возможна потеря данных при нескольких Yandex Market business ID

**Статус 17.09.2026:** исправлено в коде и миграции
`20260917_yandex_business_scope`. Finance и advertising используют business
scope для курсора, coverage и delete; уникальные ключи обеих таблиц включают
`business_id`; чужой `businessId` в строке отчёта отклоняется до изменения БД.
Production-проверка показала один бизнес, 368 рекламных и 18 173 финансовых
строк, конфликтов будущих ключей нет. Окончательное закрытие — после применения
миграции и успешного `alembic check` на production.

**Доказательства**

- `yandex_market/services/finance_service.py:93-100` ищет последнюю транзакцию без фильтра `business_id`.
- `yandex_market/services/finance_service.py:131-140` удаляет весь временной диапазон без фильтра `business_id`.
- `yandex_market/services/advertising_service.py:82-89`, `101-135` проверяет заполненность дат без business scope.
- `yandex_market/services/advertising_service.py:218-236` удаляет статистику по дате и source без `business_id`.
- Уникальность рекламы в `app/models.py:1505-1508` не включает `business_id`.
- Одновременно identity/orders явно допускают несколько business ID.

**Риск**

При переключении `YANDEX_MARKET_BUSINESS_ID` или расширении на несколько бизнесов одна синхронизация может удалить данные другой, пропустить её историю или получить конфликт уникальности.

**Исправление**

- добавить `business_id` в unique constraint рекламы отдельной миграцией;
- во все lookup/delete/coverage запросы finance и advertising добавить business scope;
- валидировать, что строки отчёта принадлежат запрошенному бизнесу;
- добавить PostgreSQL-тест: два бизнеса, повторная загрузка одного не меняет строки второго.

### P1-03. Синхронизации делают полные сканы растущих таблиц

**Доказательства**

Примеры:

- `wb/services/finance_service.py:56-58,97-98` загружает целиком справочники и все финансовые строки в Python-словари;
- `wb/services/sales_service.py:73-74,98-99` загружает все orders/sales;
- `wb/services/customer_communication_service.py:69-71,95-97` загружает всю историю вопросов, отзывов и ответов;
- `product_catalog/service.py:163-224,250-258,350-354` загружает все товары, media и attributes;
- `inventory_sync/service.py:271-274,319,357,438-440,486-488` читает все current stocks;
- дневные snapshots создаются Python-циклами по всем текущим остаткам (`inventory_sync/service.py:533-586`).

**Риск**

Время и память растут линейно от всей истории, а не от размера новой порции. Финансовые таблицы и raw JSON будут основным ограничителем. Длинные транзакции увеличат блокировки, VACUUM lag и вероятность повторного запуска после timeout.

**Исправление**

- выбирать existing rows только по ключам текущей входной пачки;
- использовать PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` и batch 1–5 тыс. строк;
- для snapshots перейти на `INSERT INTO ... SELECT ... ON CONFLICT ...`;
- использовать `yield_per`/server-side cursors только там, где действительно нужен полный проход;
- добавить метрики duration, received, inserted, updated, skipped и RSS процесса;
- зафиксировать нагрузочный baseline на объёме 10× от текущего.

### P1-04. Нет политики хранения и ограничения роста данных

**Доказательства**

В коде нет cleanup/retention задач. Бессрочно растут:

- ежедневные складские snapshots с копией `raw_data`;
- price snapshots;
- catalog snapshots с полным catalog/media/attributes JSON;
- sync runs, errors, healthcheck runs и Telegram deliveries;
- локальные документы, бухгалтерские отчёты и media-файлы.

**Риск**

Рост БД, индексов, backup window и диска приведёт к замедлению dashboard и синхронизаций либо к заполнению VPS.

**Исправление**

- согласовать retention по типу данных;
- партиционировать крупные append-only таблицы по месяцу/дате;
- хранить raw payload один раз или сжимать/выносить его в object storage;
- добавить cleanup service в dry-run режиме, затем timer;
- контролировать размеры таблиц/индексов и свободное место в healthcheck;
- никогда не удалять финансовые данные без согласованного юридического срока хранения.

### P1-05. Dashboard не масштабируется и может исчерпать ресурсы

**Доказательства**

- `ThreadingHTTPServer` создаёт поток на соединение (`dashboard/__main__.py:55-90`), worker limit отсутствует.
- Один `/api/summary` последовательно рассчитывает текущий и предыдущий периоды, две cabinet analytics выборки, рекламу, текущие и исторические остатки и series (`dashboard/service.py:633-672`).
- Тяжёлые raw SQL используют JSON traversal и агрегации на лету.
- `/api/stocks` возвращает весь каталог без пагинации (`dashboard/service.py:41-184`).
- Изображение целиком читается в RAM через `read_bytes()` (`dashboard/__main__.py:70-73`); разрешённый media-файл может быть до 512 MiB.
- `DASHBOARD_DATABASE_URL` по умолчанию наследует основной `DATABASE_URL`, то есть read-only роль не обязательна.

**Риск**

Несколько параллельных запросов способны занять все DB connections, CPU и RAM. Dashboard конкурирует с загрузчиками и может ухудшить свежесть данных.

**Исправление**

- перейти на WSGI/ASGI server с фиксированным числом workers/threads;
- сделать dedicated PostgreSQL role с обязательным `SELECT`-only URL;
- добавить `statement_timeout`, HTTP timeout/rate limit и upper bound на response rows;
- ввести pagination/фильтры в stocks;
- отдавать файлы потоково через Nginx/X-Accel-Redirect;
- кэшировать summary на 30–120 секунд или считать дневные агрегаты заранее;
- снять `EXPLAIN (ANALYZE, BUFFERS)` для трёх основных endpoints на production-like копии.

### P1-06. Бизнес-дата зависит от timezone ОС в части модулей

**Доказательства**

`date.today()` используется в `dashboard/service.py`, `wb/scheduler.py`, `wb/services/finance_service.py`, `wb/services/fbw_supply_service.py`, `wb/services/sales_service.py`, `supply_movement_report/service.py`. При этом бизнес-логика проекта в документации привязана к `Europe/Moscow`, а только inventory/Ozon/Yandex местами используют явный `ZoneInfo`.

**Риск**

На сервере в UTC с 00:00 до 02:59 по Москве dashboard может считать московскую дату «будущей», а workers — выбирать неверный конец периода.

**Исправление**

Создать единый модуль business time и использовать `datetime.now(ZoneInfo(...)).date()`. Добавить тесты на границу полуночи UTC/Europe-Moscow и DST для настраиваемых зон.

### P1-07. Тесты не защищают production-сценарий и CI отсутствует

**Доказательства**

- нет `.github/workflows`, `pyproject.toml`, Ruff, mypy/pyright, coverage gate или pre-commit;
- 242 из 243 тестов не являются integration;
- integration test (`tests/test_db.py`) делает только `SELECT 1`;
- обычный `pytest` не исключает marker `integration` и поэтому может подключиться к БД из `.env`;
- большинство persistence tests используют SQLite in-memory, не PostgreSQL;
- dashboard tests в основном проверяют наличие строк в исходнике через `inspect.getsource`, а не выполняют SQL.

**Риск**

PostgreSQL JSONB, LATERAL, advisory locks, timezone и миграции остаются непроверенными. Рефакторинг может ломать логику без падения string-based тестов. Локальный тест случайно обращается к реальной БД.

**Исправление**

- CI: lint, format check, type check, unit tests, integration tests с disposable PostgreSQL;
- по умолчанию запускать `pytest -m "not integration"`; integration — только с явным флагом и отдельным URL;
- добавить миграционные сценарии: empty DB → head и предыдущий релиз → head;
- выполнить реальные dashboard SQL smoke tests;
- добавить contract fixtures для ответов API и тесты идемпотентного повторного запуска;
- запретить integration tests при hostname/DB name, похожих на production.

### P1-08. Загрузчики файлов имеют неполные resource/SSRF ограничения

**Доказательства**

- `product_catalog/storage.py:72-106` разрешает любой HTTP(S) hostname и автоматические redirects Requests; private/loopback адреса не запрещены.
- Ozon downloader хорошо валидирует HTTPS-host и redirect, но читает `response.content` целиком до проверки лимита (`ozon/accounting_storage.py:95-125,149-162`).
- Yandex advertising также сначала читает весь `response.content`; ZIP ограничен по одному member, но нет лимита количества и суммарного распакованного размера (`yandex_market/advertising.py:82-105,124-145`).
- reconciliation читает XLSX/CSV целиком в списки без общего лимита файла/строк (`finance_reconciliation/parsing.py:131-176`).

**Риск**

Повреждённый/подменённый URL может использовать server-side request к внутренним адресам. Большой ответ или ZIP bomb способен исчерпать RAM/диск.

**Исправление**

- host allowlist по маркетплейсу, ручная обработка redirects, DNS/IP проверка каждого hop;
- streaming download с `Content-Length` precheck и инкрементальным hard limit;
- лимиты ZIP: число members, суммарный uncompressed size и compression ratio;
- лимиты reconciliation file size/rows/columns и отдельный карантин для ошибочных файлов;
- тесты private IP, redirect-to-private, oversized/chunked response и ZIP bomb metadata.

### P1-09. Рабочее дерево содержит чувствительные и генерируемые артефакты

**Доказательства**

На момент аудита:

- 76 untracked объектов;
- 53 имени с префиксом `.tmp`;
- 30 `*.bundle`;
- 20 XLSX;
- присутствует `.tmp-ozon-cookies.txt`;
- `.gitignore` не покрывает общие `.tmp-*`, `*.bundle`, корневые XLSX и cookie-файлы;
- отдельно имеются пользовательские изменения `.gitignore` и удаление `mantra_sync_documentation.md`.

В текущих отслеживаемых файлах и истории Git явных `.env`, private key, cookie или XLSX не найдено — это положительный результат, но текущие untracked файлы создают высокий риск случайного коммита.

**Исправление**

- не удаляя файлы автоматически, согласовать владельца и перенести artifacts за пределы repo;
- расширить `.gitignore` точными правилами и оставить whitelist для осознанных fixtures;
- хранить bundle/export/cookie в каталогах с правами `0700/0600`;
- подключить secret scanner в pre-commit и CI;
- добавить команду безопасной очистки только для явно определённого artifacts-каталога.

### P1-10. Зависимости не воспроизводимы

**Доказательства**

`requirements.txt` содержит широкие диапазоны, не содержит lock/hashes и смешивает runtime с `pytest`. Верхние границы заданы не для всех пакетов. Текущее окружение работает на Python 3.13.15, а документация обещает Python 3.11+ без CI-матрицы.

**Риск**

Два деплоя могут получить разные версии. Новый major/minor transitive package способен сломать worker после обычного `pip install -r requirements.txt`.

**Исправление**

- разделить direct/runtime и dev зависимости;
- генерировать lock/constraints с hashes;
- тестировать минимум поддерживаемую и production Python-версию;
- добавить `pip-audit`/Dependabot и регламент обновления lock-файла;
- не обновлять production зависимости без CI и smoke test.

### P1-11. Два независимых механизма создания схемы

**Доказательства**

`app/main.py:5-8` вызывает `Base.metadata.create_all()`, а основной механизм — Alembic. Документация предупреждает, что `create_all` не заменяет миграции, но команда остаётся доступной.

**Риск**

На новой БД `create_all` создаст latest-таблицы без записи Alembic revision. Последующий `alembic upgrade` попытается создать их повторно. Возникает трудно диагностируемый schema drift.

**Исправление**

Удалить production entry point либо разрешать его только для disposable test DB через явный флаг. Все реальные окружения создавать только `alembic upgrade head`.

### P2-01. Главный WB worker не имеет межпроцессного lock

**Доказательства**

`wb/scheduler.py:68,73-77` защищён только `self._running` внутри одного процесса. Ozon, Yandex, inventory, prices и catalog используют PostgreSQL advisory locks.

**Риск**

Ручной запуск параллельно systemd service либо второй экземпляр deployment создаст гонки, повторные API-вызовы и конфликтующие commits.

**Исправление**

Добавить session-level advisory lock для полного WB cycle или отдельные locks для независимых задач. Отдельно определить ожидаемое поведение: exit 0 со статусом skipped, а не crash/restart storm.

### P2-02. Настройки SQLAlchemy engine подходят не всем процессам

**Доказательства**

`app/db.py:6-7` использует engine defaults: нет `pool_pre_ping`, `pool_recycle`, `connect_timeout`, `application_name` и явного ограничения pools. Каждый systemd process создаёт собственный pool; dashboard создаёт ещё один engine.

**Риск**

После сетевого сбоя возможны stale connections. При параллельных timers и dashboard число соединений плохо прогнозируется, а в `pg_stat_activity` трудно определить владельца.

**Исправление**

Ввести централизованный engine factory: разные профили для long-running worker, one-shot task и dashboard; задать `pool_size/max_overflow`, `pool_pre_ping`, connect timeout и `application_name`. Для коротких one-shot jobs рассмотреть `NullPool`.

### P2-03. Смешаны naive и timezone-aware timestamp

**Доказательства**

В `app/models.py` найдено 43 naive `DateTime` колонки и 155 timezone-aware. Есть 44 текстовых вхождения `datetime.utcnow`; Python 3.13 уже выдаёт 122 SQLAlchemy deprecation warnings в тестах. Часть WB кода вручную удаляет timezone через `.replace(tzinfo=None)`.

**Риск**

Ошибки сравнения времени, неверные границы отчётов и болезненная будущая миграция. Предупреждения маскируют новые регрессии.

**Исправление**

Поэтапно перевести технические timestamps на aware UTC, бизнес-даты — на явный timezone helper. Сделать миграции небольшими, с явной интерпретацией существующих naive значений. После миграции включить warnings-as-errors для нового кода.

### P2-04. Ошибки могут переносить лишние данные в БД, логи и Telegram

**Доказательства**

- HTTP-клиенты включают `response.text` в исключения (`wb/client.py`, `ozon/client.py`, `yandex_market/client.py`).
- WB logger сохраняет полный traceback, при этом recursive redaction применяется к details, но не к строке traceback (`wb/sync_logging.py:54-76`).
- operations bot пересылает тексты ошибок в Telegram.

**Риск**

Тело ответа внешнего API может содержать идентификаторы заказов, покупателей или диагностические данные. Оно окажется одновременно в journal, PostgreSQL, JSONL и Telegram.

**Исправление**

Сделать единый sanitizer: allowlist полей, ограниченный excerpt, удаление URL credentials/tokens/PII. В operational Telegram передавать error code/correlation ID, а подробности оставлять в защищённом журнале с retention.

### P2-05. Hardening systemd применяется непоследовательно

**Доказательства**

`wbozon-ozon@`, `wbozon-yandex-market@`, prices, product-catalog и product-mapping не имеют `NoNewPrivileges` и `PrivateTmp`. Только dashboard и relay используют `ProtectSystem=strict`. Ни один application unit не задаёт `MemoryMax`, `CPUQuota`, `TasksMax` или `RestrictAddressFamilies` в полном объёме.

**Риск**

Ошибка скачивания или обработки отчёта может исчерпать ресурсы всего VPS; компрометация процесса получает лишний доступ к файловой системе.

**Исправление**

Создать общий hardening baseline и осознанные исключения для каталогов записи. Добавить resource limits, `ProtectHome`, `ProtectSystem`, `ReadWritePaths`, `CapabilityBoundingSet`, `RestrictAddressFamilies`; проверить `systemd-analyze security` и реальные записи workers.

### P2-06. Крупные модули и raw SQL концентрируют слишком много ответственности

**Доказательства**

- `app/models.py` — 2 260 строк и 106 таблиц;
- `inventory_sync/service.py` — 774 строки;
- `dashboard/service.py` — 719 строк;
- `operations_bot/service.py` — 690 строк;
- `healthcheck/__main__.py` — 568 строк;
- `telegram_bot/reports.py` — 565 строк.

Часть файлов использует несколько операторов на строке. Единого formatter/linter/type checker нет.

**Риск**

Любая правка dashboard finance или общей модели затрагивает большой контекст, затрудняет review и провоцирует строковые тесты вместо поведенческих.

**Исправление**

- разделить models по bounded context, сохранив единый metadata registry;
- вынести dashboard SQL в query/repository layer с именованными DTO;
- разделить orchestration, parsing и persistence;
- включить Ruff formatter/lint и постепенную строгую типизацию новых/критичных модулей;
- запрещать новые однострочные блоки с несколькими операторами.

### P3-01. Документация частично устарела

**Доказательства**

`app/README.md:8,16` упоминает `session_scope()`, которого в рабочем коде нет. История диалога содержит незавершённый список действий 09.08.2026, но он не связан с issue/status. Рабочее дерево содержит локальный `mantra_sync`, тогда как канонический контекст запрещает его восстанавливать; каталог игнорируется Git и не относится к отслеживаемой архитектуре.

**Исправление**

Убрать несуществующий API из README, преобразовать открытые пункты chat summary в backlog с актуальным статусом и явно отделить local artifacts/legacy от production code.

## 6. Рекомендуемый порядок исправления

### Первые 24 часа

1. Зафиксировать, какая БД указана текущим `DATABASE_URL` и какие окружения реально существуют.
2. Подтвердить наличие свежего внешнего backup; если его нет — создать до любых миграций.
3. Восстановить копию БД и прорепетировать 22 миграции до head.
4. Добавить smoke tests актуальной PostgreSQL-схемы и ключевых dashboard SQL.
5. Карантинировать `.tmp-ozon-cookies.txt`, XLSX и bundle вне Git workspace; ничего не удалять без проверки владельца.
6. Приостановить деплой актуального кода в отстающую БД.

### Первая неделя

1. Исправить business scope Yandex finance/advertising и добавить миграцию unique constraint.
2. Настроить автоматический backup + restore verification.
3. Создать CI с disposable PostgreSQL и безопасным разделением unit/integration.
4. Исправить бизнес-даты на единую timezone abstraction.
5. Добавить advisory lock основному WB worker.
6. Закрепить зависимости lock-файлом и включить security scan.
7. Закрыть SSRF/resource-limit пробелы скачивания.

### 2–4 недели

1. Перевести самые тяжёлые sync paths на batch upsert; начать с WB finance и sales.
2. Ввести retention/partitioning и мониторинг роста.
3. Ограничить dashboard workers, добавить pagination/cache и read-only DB role.
4. Настроить engine profiles и connection budgets.
5. Унифицировать redaction и error correlation IDs.

### 1–2 месяца

1. Разделить `app/models.py` и крупные services по доменам.
2. Выделить typed query layer dashboard.
3. Завершить миграцию naive timestamps.
4. Ввести SLO: свежесть данных, длительность sync, доля partial/failed, backup age, DB/disk growth.

## 7. Минимальные release gates

Следующий релиз не должен считаться готовым без следующих автоматических проверок:

```text
unit tests без внешних ресурсов
PostgreSQL integration tests в отдельной БД
empty DB -> alembic head
previous release DB -> alembic head
alembic check
Ruff format/lint
dependency vulnerability scan
CLI smoke tests
dashboard SQL/API smoke tests
backup freshness + periodic restore test
```

## 8. Что уже сделано хорошо и должно быть сохранено

- модульный монолит соответствует текущему масштабу лучше преждевременных микросервисов;
- у Ozon/Yandex/inventory/price/catalog есть advisory locks и persistent run journals;
- inventory фиксирует данные одного marketplace одной транзакцией;
- хранение файлов использует atomic replace и проверку выхода за storage root;
- dashboard доступен через loopback + VPN-only Nginx, TLS и Basic Auth;
- Ozon/Yandex report download проверяет допустимые host suffixes и redirects;
- Telegram token редактируется в transport errors;
- один Alembic head и полная offline-цепочка миграций компилируется;
- текущие 243 теста дают хорошую базу для дальнейшего усиления, хотя пока недостаточны как release gate.

## 9. Итоговая оценка

Архитектурно проект можно развивать без переписывания с нуля. Главная задача — превратить быстро выросший набор интеграций в управляемую production-систему: синхронизировать схему, защитить данные backup-ами, перенести проверку PostgreSQL и миграций в CI, затем убрать O(N) full-table загрузки и ограничить рост истории.

До устранения **P0-01** актуальную версию кода нельзя безопасно считать совместимой с БД текущего окружения.
