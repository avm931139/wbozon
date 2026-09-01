# Развертывание независимых systemd-процессов

Файлы в этом каталоге реализуют production-схему из [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md). Постоянные workers разделены по ответственности, а периодические операции оформлены как oneshot-service с timer. Адреса двух VPS, SSH/Git-доступ, PostgreSQL и диагностика relay описаны в [`docs/VPS_RUNBOOK.md`](../../docs/VPS_RUNBOOK.md).

## Установка unit-файлов

```bash
cd /home/wbozon/wbozon
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/wbozon-*.service /etc/systemd/system/wbozon-*.timer
```

Все прикладные units работают от `wbozon`, читают `/home/wbozon/wbozon/.env` и используют виртуальное окружение проекта. Если путь или пользователь отличаются, unit-файлы нужно изменить перед копированием.

## Переход со старого общего inventory service

Сначала примените миграцию, затем остановите старый общий процесс и включите три изолированных workers:

```bash
./.venv/bin/python -m alembic upgrade head
sudo systemctl disable --now wbozon-inventory.service
sudo systemctl enable --now \
  wbozon-inventory@wb.service \
  wbozon-inventory@ozon.service \
  wbozon-inventory@yandex_market.service
```

Не запускайте старый `wbozon-inventory.service` одновременно с новыми instances. Режим `--marketplace all` оставлен только для совместимости и ручной диагностики.
Шаблон дополнительно содержит `Conflicts=wbozon-inventory.service`, а advisory locks совместимого режима пересекаются со всеми тремя новыми locks.

Если Яндекс Маркет не настроен, не включайте `wbozon-inventory@yandex_market.service`; healthcheck также не требует его без `YANDEX_MARKET_CAMPAIGN_IDS`.

## Основные сервисы и Telegram

```bash
sudo systemctl enable --now \
  wbozon-wb.service \
  wbozon-telegram-relay.service \
  wbozon-telegram.service \
  wbozon-telegram-stock.timer \
  wbozon-healthcheck.timer
```

После настройки `OPERATIONS_TG_CHAT_ID` включите личный операционный дайджест:

```bash
sudo systemctl enable --now wbozon-operations.timer
sudo systemctl start wbozon-operations.service
sudo journalctl -u wbozon-operations.service -n 50 --no-pager
```

Он читает журналы БД и не является зависимостью WB/Ozon/inventory. Ошибка Telegram оставляет события в очереди и не меняет статус исходной синхронизации.

`wbozon-telegram-relay.service` нужен на текущем VPS из-за блокировки Telegram. В среде с прямым доступом relay можно не включать и удалить `WB_TG_PROXY_URL` из `.env`.

После включения `wbozon-telegram-stock.timer` удалите старую cron-строку `python -m telegram_bot --once stock-files`, иначе возможны параллельные попытки. Дедупликация защищает от повторной доставки, но второй механизм расписания не нужен.

## Документы и бухгалтерия Wildberries

Этот контур запускается отдельной oneshot-задачей и не входит в постоянный
`wbozon-wb.service`. Для токена `WB_API_KEY` должны быть разрешены категории
Wildberries «Документы» и «Финансы». Сначала примените миграцию и выполните
ручную проверку:

```bash
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m wb.document_sync --all-history --download-limit 5
```

Если команда завершилась со статусом `completed`, включите ежедневный timer:

```bash
sudo systemctl enable --now wbozon-wb-documents.timer
sudo systemctl start wbozon-wb-documents.service
sudo journalctl -u wbozon-wb-documents.service -n 100 --no-pager
```

После успешного production-запуска добавьте в `.env`
`WB_DOCUMENT_SYNC_REQUIRED=true`. Тогда healthcheck будет проверять timer,
последний статус и свежесть журнала `wb_document_sync_runs`. Файлы сохраняются
в `data/wb/documents/` и требуют отдельного резервного копирования. Полная схема
и ограничения API описаны в [`wb/DOCUMENTS.md`](../../wb/DOCUMENTS.md).

## Ozon timers

```bash
sudo systemctl enable --now \
  wbozon-ozon-products.timer \
  wbozon-ozon-orders.timer \
  wbozon-ozon-supplies.timer \
  wbozon-ozon-daily-sales.timer \
  wbozon-ozon-finances.timer \
  wbozon-ozon-ads.timer
```

Документы и бухгалтерия сначала проверяются вручную, потому что первый запуск
создаёт асинхронные отчёты и может не сразу получить готовые файлы:

```bash
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m ozon --task documents
sudo systemctl enable --now wbozon-ozon-documents.timer
sudo systemctl start wbozon-ozon@documents.service
sudo journalctl -u wbozon-ozon@documents.service -n 100 --no-pager
```

После успешного запуска добавьте `documents` в `OZON_REQUIRED_TASKS`. Файлы
`data/ozon/accounting/` требуют отдельной резервной копии. Полное описание — в
[`ozon/ACCOUNTING.md`](../../ozon/ACCOUNTING.md).

Сверка отправленного и фактически принятого FBO-количества выполняется отдельной
ежедневной задачей. Первый исторический запуск выполните вручную:

```bash
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m ozon --task supply_reconciliation
sudo systemctl enable --now wbozon-ozon-supply-reconciliation.timer
sudo systemctl start wbozon-ozon@supply_reconciliation.service
sudo journalctl -u wbozon-ozon@supply_reconciliation.service -n 100 --no-pager
```

Timer срабатывает в 03:20 МСК с задержкой до пяти минут. После успешного запуска
добавьте `supply_reconciliation` в `OZON_REQUIRED_TASKS`. Подробная схема и SQL
для поиска расхождений находятся в
[`ozon/SUPPLY_RECONCILIATION.md`](../../ozon/SUPPLY_RECONCILIATION.md).

`communications` на текущем кабинете не включается: Questions API доступен, но Reviews API отвечает HTTP 403. После выдачи доступа проверьте ручной запуск и только затем включите timer:

```bash
sudo systemctl start wbozon-ozon@communications.service
sudo journalctl -u wbozon-ozon@communications.service -n 50 --no-pager
sudo systemctl enable --now wbozon-ozon-communications.timer
```

## Проверка

```bash
systemctl --no-pager --full status \
  wbozon-wb.service \
  wbozon-inventory@wb.service \
  wbozon-inventory@ozon.service \
  wbozon-inventory@yandex_market.service \
  wbozon-wb-documents.timer \
  wbozon-telegram.service \
  wbozon-telegram-relay.service \
  wbozon-operations.timer

systemctl list-timers 'wbozon-*' --all
sudo systemctl start wbozon-healthcheck.service
sudo journalctl -u wbozon-healthcheck.service -n 100 --no-pager
```

`inactive (dead)` нормально только для успешно завершившихся oneshot services. Постоянные `wbozon-wb.service`, `wbozon-inventory@*.service`, `wbozon-telegram.service` и relay должны быть `active (running)`.

Календарь timers задан в `Europe/Moscow`; поле `NEXT` выводится systemd в локальной временной зоне VPS.
