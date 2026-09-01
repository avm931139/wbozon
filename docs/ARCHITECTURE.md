# Архитектура процессов wbozon

## Модель развертывания

`wbozon` — модульный монолит с независимыми worker-процессами. Это не набор сетевых микросервисов: процессы используют один репозиторий, одно Python-окружение, общую конфигурацию и общую PostgreSQL. При этом каждый рабочий контур имеет отдельную точку запуска и отдельный systemd unit, поэтому сбой или перезапуск одного контура не останавливает остальные.

Все прикладные процессы и PostgreSQL работают на production VPS `185.105.111.112`. Legacy VPS `46.30.47.95` выполняет только роль SSH/SOCKS relay к Telegram и не является вторым экземпляром приложения. Эксплуатационная схема описана в [`VPS_RUNBOOK.md`](VPS_RUNBOOK.md).

Процессы не вызывают друг друга напрямую. Интеграционные workers получают данные из внешних API и сохраняют их в PostgreSQL; Telegram и healthcheck читают уже сохранённое состояние.

## Рабочие процессы

| Контур | Точка запуска | systemd | Назначение |
|---|---|---|---|
| Wildberries | `python -m wb` | `wbozon-wb.service` | общий WB-цикл без Telegram и остатков |
| Документы WB | `python -m wb.document_sync` | `wbozon-wb-documents.timer` | метаданные и файлы документов, снимок баланса; ежедневно и независимо от WB worker |
| Ozon | `python -m ozon --task <task>` | `wbozon-ozon@<task>.service` и отдельные timers | независимые задания каталога, заказов, поставок, продаж, финансов и рекламы |
| Документы Ozon | `python -m ozon --task documents` | `wbozon-ozon-documents.timer` | асинхронные бухгалтерские отчёты, локальные файлы и JSON-снимки |
| Остатки WB | `python -m inventory_sync --marketplace wb` | `wbozon-inventory@wb.service` | WB FBS/FBO и дневные срезы |
| Остатки Ozon | `python -m inventory_sync --marketplace ozon` | `wbozon-inventory@ozon.service` | агрегатные и складские остатки Ozon и дневные срезы |
| Остатки Яндекс Маркета | `python -m inventory_sync --marketplace yandex_market` | `wbozon-inventory@yandex_market.service` | остатки кампаний и дневные срезы |
| Telegram-тексты | `python -m telegram_bot` | `wbozon-telegram.service` | утренние и оперативные отчёты |
| Telegram Excel | `python -m telegram_bot --once stock-files` | `wbozon-telegram-stock.timer` | три складских файла в 09:00 МСК |
| Личный журнал | `python -m operations_bot` | `wbozon-operations.timer` | дайджест успешных и ошибочных действий программы |
| Healthcheck | `python -m healthcheck` | `wbozon-healthcheck.timer` | процессы, свежесть БД, срезы и доставка Telegram |
| Telegram relay | SSH dynamic SOCKS proxy | `wbozon-telegram-relay.service` | доступ к Telegram через старый VPS |

`main.py` оставлен только как совместимый alias для `python -m wb`. Он больше не запускает Telegram в одном процессе с WB.

## Изоляция отказов

- WB, Ozon, Яндекс Маркет и Telegram работают в разных процессах.
- Три inventory worker используют разные PostgreSQL advisory locks и отдельные записи `inventory_sync_runs.marketplace`.
- Ошибка API одного маркетплейса не откатывает текущие остатки и дневной срез другого маркетплейса.
- Каждый Ozon task имеет собственный advisory lock и запись в `ozon_sync_runs`.
- Excel-файлы имеют независимые ключи доставки: уже отправленный файл не дублируется при повторе другого.
- Личные уведомления читают завершённые события из БД через собственную очередь; недоступность Telegram не меняет результат workers.
- Общими точками отказа остаются PostgreSQL, каталог проекта, `.venv`, `.env` и сам VPS.

Журналы процессов также разделены: WB пишет в `logs/wb/`, Telegram — в `logs/telegram/`, остальные workers — в journal systemd и свои таблицы запусков. Два процесса не ротируют один файл одновременно.

## Границы данных

```text
WB API ───────────────→ wb worker ───────────────┐
WB stock APIs ────────→ inventory@wb ───────────┤
Ozon APIs ────────────→ ozon tasks ─────────────┤
Ozon stock APIs ──────→ inventory@ozon ─────────┤→ PostgreSQL
Yandex Market API ────→ inventory@yandex_market ┤
                                                   ├→ telegram workers → Telegram API
                                                   ├→ operations_bot → личный Telegram
                                                   └→ healthcheck → Telegram API
```

Общие ORM-модели находятся в `app/models.py`; схема изменяется только миграциями Alembic. Межпроцессного Python state и общей памяти нет.

## Совместимые диагностические режимы

`python -m inventory_sync --marketplace all` и `python -m ozon --once` сохранены для ручной диагностики. В production они не используются: объединённый inventory-режим снова связывает доступность всех API одной транзакцией, а общий Ozon-цикл уступает отдельным timers по наблюдаемости и перезапуску.
