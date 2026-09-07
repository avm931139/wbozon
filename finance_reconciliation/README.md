# Сверка финансовых отчётов кабинетов

Независимая задача сравнивает вручную выгруженные финансовые отчёты WB, Ozon и
Яндекс Маркета с уже сохранёнными финансовыми данными API. Она не вызывает API
маркетплейсов, не использует оперативные заказы, рекламу или остатки и не влияет
на их фоновые процессы.

## Папки и имена файлов

Входящая папка по умолчанию:

```text
/home/wbozon/wbozon/data/finance_reconciliation/inbox/
```

Поддерживаются `.xlsx` и `.csv`. Для надёжного определения кабинета используйте
имена `wb_финансы_2026-08.xlsx`, `ozon_финансы_2026-08.csv` или
`yandex_market_финансы_2026-08.xlsx`.

Исходные файлы не перемещаются, не изменяются и не удаляются. SHA-256 файла
записывается в `finance_reconciliation_runs`, поэтому одинаковый файл повторно
не проверяется. Изменённый файл считается новой версией.

Результаты сохраняются в `data/finance_reconciliation/reports/` и содержат
итог, отсутствующие с каждой стороны строки, расхождения сумм и совпавшие строки.
Статус `КОРРЕКТНО` выдаётся только при совпадении ключей, кратности и сумм с
допуском `FINANCE_RECONCILIATION_TOLERANCE`.

## Запуск

```bash
./.venv/bin/python -m alembic upgrade head
mkdir -p data/finance_reconciliation/inbox data/finance_reconciliation/reports
./.venv/bin/python -m finance_reconciliation --no-telegram
```

Один файл:

```bash
./.venv/bin/python -m finance_reconciliation \
  --file data/finance_reconciliation/inbox/wb_финансы_2026-08.xlsx \
  --marketplace wb
```

Для повторной проверки того же файла после обновления данных API добавьте
`--force`. Автоматический сканер повторно не отправляет уже обработанный SHA-256.

Автоматическая проверка и отправка результата в личный Telegram:

```bash
sudo cp deploy/systemd/wbozon-finance-reconciliation.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wbozon-finance-reconciliation.timer
sudo systemctl start wbozon-finance-reconciliation.service
sudo journalctl -u wbozon-finance-reconciliation.service -n 100 --no-pager
```

По умолчанию используются `OPERATIONS_TG_*`. Отдельный бот или чат задаются
переменными `FINANCE_RECONCILIATION_TG_*`.

## Правила сопоставления

- WB: `rrdId`/номер строки и `forPay`/«К перечислению продавцу»;
- Ozon: ID, тип и дата операции плюс сумма операции;
- Яндекс Маркет: ID транзакции либо заказ/SKU/тип/дата и `transactionSum`.

Неизвестная структура, неопределённый период или отсутствие данных API считаются
ошибкой распознавания, а не успешной сверкой. После первого реального файла
каждого кабинета его точные заголовки следует закрепить тестом адаптера.
