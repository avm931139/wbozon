# Отчёт по поставкам и возвратам товаров

Формирует один Excel за весь доступный период с отдельными листами поставок и
обратного движения для Wildberries, Ozon и Яндекс Маркета. Строки отсортированы
и сгруппированы по идентификатору поставки/заявки.

Источники:

- WB поставки — сохранённые заявки FBW и их товары (`quantity`,
  `acceptedQuantity`, `readyForSaleQuantity`);
- WB возвраты — официальный отчёт `GET /api/v1/analytics/goods-return`;
- Ozon поставки — сохранённый состав `/v1/supply-order/bundle` и акты приёмки;
- Ozon возвраты — `/v1/removal/from-stock/list` и
  `/v1/removal/from-supply/list`;
- Яндекс Маркет — заявки `SUPPLY`, `WITHDRAW`, `UTILIZATION` и их товары из
  `/v2/campaigns/{campaignId}/supply-requests*`.

Если источник одной площадки недоступен, остальные листы всё равно строятся, а
проблема попадает на лист `Ошибки источников`. Пустой лист не считается нулевым
движением без проверки этого листа.

Запуск:

```bash
./.venv/bin/python -m supply_movement_report
```

Результат:

```text
data/supply_movement_reports/marketplace_supplies_and_returns_all.xlsx
```

Отправка в личный операционный Telegram:

```bash
./.venv/bin/python -m supply_movement_report --send-telegram
```

Для быстрой диагностики без длительных запросов истории возвратов WB/Ozon:

```bash
./.venv/bin/python -m supply_movement_report --without-live-returns
```
