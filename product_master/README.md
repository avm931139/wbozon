# Единый справочник товаров

`product_master` связывает карточки одного физического товара между Wildberries, Ozon и Яндекс Маркетом. Источники артикула:

- WB — `wb_products.vendor_code`;
- Ozon — `ozon_products.offer_id`;
- Яндекс Маркет — `yandex_market_offers.offer_id`.

Запуск:

```bash
python -m product_master
```

Артикул приводится к верхнему регистру, внешние пробелы удаляются. Точные совпадения получают `match_method=exact`. Тестовые дополнения `_D`, `__D`, `_D1`, `_DD`, ` OLD`, `_TEST` и `_ТЕСТ` удаляются только тогда, когда полученный базовый артикул действительно присутствует в каталоге. Такая связь получает `match_method=suffix` и `is_test_variant=true`. Неизвестный артикул не объединяется по частичному сходству и остаётся отдельным товаром.

Ручная связь с `match_method=manual` имеет приоритет и не перезаписывается автоматическим запуском.

Таблицы:

- `master_products` — один внутренний товар на базовый артикул;
- `marketplace_product_links` — все карточки и тестовые варианты площадок;
- `product_mapping_runs` — журнал запусков и ошибок.

В `marketplace_current_prices` и `marketplace_price_snapshots` записывается `master_product_id`. Транзакционные данные можно присоединять через `marketplace_product_links`, не изменяя исходные идентификаторы заказов, остатков или финансов.

Пример просмотра соответствий:

```sql
SELECT mp.article,
       mpl.marketplace,
       mpl.source_article,
       mpl.external_product_id,
       mpl.match_method,
       mpl.is_test_variant
FROM master_products mp
JOIN marketplace_product_links mpl ON mpl.master_product_id = mp.id
WHERE mp.active AND mpl.active
ORDER BY mp.article, mpl.marketplace, mpl.source_article;
```

Production-расписание обновляет соответствия ежедневно после ночных обновлений каталогов. Свежесть контролирует healthcheck, а результат или расшифровку ошибки отправляет личный операционный Telegram-бот.
