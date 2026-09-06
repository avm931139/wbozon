# История цен маркетплейсов

Независимый модуль получает цены из кабинетов Wildberries, Ozon и Яндекс Маркета. Каждые три часа он обновляет текущую цену и всегда добавляет новый неизменяемый снимок, даже если цена не изменилась.

## Команды

```bash
python -m price_sync --marketplace wb
python -m price_sync --marketplace ozon
python -m price_sync --marketplace yandex_market
```

Сбой одного кабинета не откатывает и не блокирует два остальных. Повторный одновременный запуск одного кабинета блокируется PostgreSQL advisory lock.

## Таблицы

- `marketplace_current_prices` — последнее известное состояние товара/размера;
- `marketplace_price_snapshots` — полная история с точным `captured_at` и `run_id`;
- `marketplace_price_sync_runs` — журнал успешных и ошибочных запусков.

Основные цены: исходная (`list_price`), установленная продавцом (`seller_price`), показываемая покупателю, если API её возвращает (`customer_price`), клубная (`club_price`) и минимальная допустимая (`min_price`). Идентификаторы оффера, товара и размера сохранены отдельно — это позволит позже связать цены с себестоимостью и собственными остатками. Полный ответ API хранится в `raw_data`.

Ограничения источников:

- Ozon прямо возвращает текущие маркетинговые акции, их названия и настройку автоматического участия;
- WB возвращает базовую, скидочную и WB Club цену, но этот метод не сообщает название акции;
- Яндекс Маркет возвращает установленную продавцом цену, зачёркнутую цену и порог «Бестселлера». Это не гарантирует совпадение с итоговой ценой покупателя после скидок самого Маркета.

## Поиск изменений и подозрительных цен

```sql
WITH history AS (
    SELECT marketplace, source_key, offer_id, product_name, captured_at,
           customer_price, seller_price,
           lag(coalesce(customer_price, seller_price)) OVER (
               PARTITION BY marketplace, source_key ORDER BY captured_at
           ) AS previous_price
    FROM marketplace_price_snapshots
)
SELECT *,
       round(100 * (coalesce(customer_price, seller_price) - previous_price)
             / nullif(previous_price, 0), 2) AS change_percent
FROM history
WHERE previous_price IS DISTINCT FROM coalesce(customer_price, seller_price)
ORDER BY captured_at DESC;
```

Для Ozon товары, которые API прямо пометил участниками акции:

```sql
SELECT offer_id, product_name, customer_price, promotion_names, captured_at
FROM marketplace_current_prices
WHERE marketplace = 'ozon' AND active AND in_promotion IS TRUE
ORDER BY product_name;
```

Миграция: `20260906_marketplace_prices`. Допустимая давность последнего успешного запуска для healthcheck задаётся `PRICE_SYNC_MAX_AGE_SECONDS` (по умолчанию четыре часа).
