# Сверка FBO-поставок Ozon

Независимое задание `python -m ozon --task supply_reconciliation` загружает
отправленное и фактически принятое Ozon количество по каждой поставке и SKU.
История начинается с `OZON_SUPPLY_RECONCILIATION_FROM=2026-01-01` и продолжается
до текущего момента.

## Источники

1. `/v3/supply-order/list` и `/v3/supply-order/get` — заявки, поставки,
   `supply_id`, `bundle_id`, статус и склад хранения.
2. `/v1/supply-order/bundle` — заявленный товарный состав и отправленное
   количество по SKU.
3. `/v1/supply-order/act/summary/get` — список и состояние актов поставки.
4. `/v1/supply-order/act/product/get` — заявленное, фактическое и согласованное
   количество по SKU для каждого акта.

Обрабатываются поставки, которые уже были переданы Ozon: приняты на точке
отгрузки, находятся в пути или на приёмке, ожидают согласования актов, находятся
в споре, завершены либо отклонены на точке отгрузки. Черновики, отменённые и ещё
не отправленные заявки в сверку не входят.

## Хранение

- `ozon_fbo_supply_declared_items` — заявленный состав из `bundle`;
- `ozon_fbo_supply_acts` — сводные данные и состояние каждого акта;
- `ozon_fbo_supply_act_items` — фактические строки актов по SKU;
- `ozon_fbo_supply_reconciliation` — SQL-представление для анализа расхождений;
- `ozon_sync_runs` с `task=supply_reconciliation` — журнал запусков.

Все исходные ответы сохраняются в `raw_data`. Повторный запуск обновляет строки
по устойчивым ключам `supply_id + sku`, `act_id` и `act_id + sku`, не создавая
дубликатов.

Основной запрос для анализа:

```sql
SELECT
    supply_order_id,
    supply_id,
    sku,
    offer_id,
    storage_warehouse_name,
    sent_quantity,
    accepted_quantity,
    is_acceptance_completed,
    quantity_difference,
    defect_fact_quantity,
    surplus_fact_quantity,
    shortcoming_fact_quantity
FROM ozon_fbo_supply_reconciliation
WHERE is_acceptance_completed
  AND (quantity_difference <> 0
   OR defect_fact_quantity <> 0
   OR surplus_fact_quantity <> 0
   OR shortcoming_fact_quantity <> 0)
ORDER BY supply_order_id, supply_id, sku;
```

`accepted_quantity` — сумма `fact_quantity` только по актам типа `ACCEPTANCE`.
Остальные типы актов сохранены отдельно, чтобы излишки, брак и недостачи не
смешивались с фактической приёмкой. Для окончательной сверки используйте только
строки с `is_acceptance_completed=true`: поставки в пути иначе закономерно имели
бы нулевую приёмку и выглядели бы как недостача. `quantity_difference` считается
как `accepted_quantity - sent_quantity`: отрицательное значение означает
недостачу, положительное — излишек.

HTTP 404 при запросе акта означает, что акт для поставки ещё не сформирован. Это
штатное состояние для поставок в пути и не делает запуск ошибочным. Остальные
ошибки дают статус `partial`, сохраняются в `ozon_sync_runs` и отправляются личным
операционным Telegram-ботом.

Для методов актов используется отдельная, более осторожная частота запросов:
`OZON_SUPPLY_RECONCILIATION_REQUEST_PAUSE_SECONDS` (по умолчанию 1 секунда).
После того как короткие повторы HTTP-клиента исчерпаны, HTTP 429 повторяется на
уровне конкретной операции до `OZON_SUPPLY_RECONCILIATION_RATE_LIMIT_RETRIES`
раз с экспоненциальной паузой, начинающейся с
`OZON_SUPPLY_RECONCILIATION_RATE_LIMIT_BACKOFF_SECONDS`. Уже записанные строки
коммитятся независимо и при таком повторе не теряются и не дублируются.

## Расписание и первый запуск

Timer `wbozon-ozon-supply-reconciliation.timer` запускает задачу ежедневно в
03:20 `Europe/Moscow` с задержкой до пяти минут. Это соответствует требуемому
окну после полуночи и до 06:00.

```bash
cd /home/wbozon/wbozon
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m ozon --task supply_reconciliation
sudo cp deploy/systemd/wbozon-ozon@.service /etc/systemd/system/
sudo cp deploy/systemd/wbozon-ozon-supply-reconciliation.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wbozon-ozon-supply-reconciliation.timer
sudo systemctl start wbozon-ozon@supply_reconciliation.service
sudo journalctl -u wbozon-ozon@supply_reconciliation.service -n 100 --no-pager
```

После успешного ручного запуска добавьте `supply_reconciliation` в
`OZON_REQUIRED_TASKS`, чтобы healthcheck контролировал ежедневную свежесть.
