# Wildberries API: полный каталог методов

Документ составлен 30 августа 2026 года по 13 официальным OpenAPI-категориям
портала WB. Машинные снимки получены 19 августа 2026 года из страниц Swagger и
официальной документации; для воспроизводимого анализа использован commit
[`6f56592`](https://github.com/MissiaL/wildberries-api/tree/6f56592666e423bf587da06fe204d287094c3a38/assets/openapi)
инструментального репозитория со снимками исходных схем.

Канонический источник: [портал разработчиков WB](https://dev.wildberries.ru/docs/openapi/api-information).
Официальный портал подтверждает, что документация разделена на категории и
предоставляется в формате OpenAPI 3.0 с отдельным `swagger.yaml` для каждой
категории.

Всего в снимке: **286 операций**. По HTTP-методам:
`DELETE` — 10, `GET` — 123, `PATCH` — 13, `POST` — 125, `PUT` — 15.
Операций с признаком `deprecated`: **0**. Отсутствие такой
пометки не отменяет необходимость проверять журнал изменений и дату отключения
старых версий.

Обозначение **РЕАЛИЗОВАНО** означает, что сочетание host + HTTP method + path
используется текущим кодом проекта.

## Авторизация и архитектура

- Авторизация выполняется токеном в заголовке `Authorization`.
- Токен действует 180 дней; доступ определяется категорией и битовой маской
  прав. Есть персональные, сервисные, базовые и тестовые токены, а также флаг
  read-only.
- В отличие от Ozon и Яндекс Маркета, WB использует много разных host-ов:
  `content-api`, `marketplace-api`, `statistics-api`, `seller-analytics-api`,
  `advert-api`, `feedbacks-api`, `supplies-api`, `finance-api` и другие.
- Лимиты задаются для каждой операции и типа токена. При превышении возвращается
  `429`; нужно учитывать `Retry-After` и заголовки `X-RateLimit-*`.
- Метод `/ping` существует на каждом сервисном host-е. Он ограничен тремя
  запросами за 30 секунд и не предназначен для частого мониторинга.
- Для части категорий доступны sandbox-host-ы и тестовый токен, однако Swagger с
  рабочим токеном обращается к реальным данным.

## Категории

| № | Категория | Операций | Основные host-ы |
|---:|---|---:|---|
| 1 | [Общее](https://dev.wildberries.ru/docs/openapi/api-information) | 10 | `common-api.wildberries.ru`, `content-api.wildberries.ru`, `seller-analytics-api.wildberries.ru`, `discounts-prices-api.wildberries.ru`, `marketplace-api.wildberries.ru`, `statistics-api.wildberries.ru`, `advert-api.wildberries.ru`, `feedbacks-api.wildberries.ru`, `buyer-chat-api.wildberries.ru`, `supplies-api.wildberries.ru`, `returns-api.wildberries.ru`, `documents-api.wildberries.ru`, `finance-api.wildberries.ru`, `user-management-api.wildberries.ru` |
| 2 | [Работа с товарами](https://dev.wildberries.ru/docs/openapi/work-with-products) | 52 | `content-api.wildberries.ru`, `discounts-prices-api.wildberries.ru`, `marketplace-api.wildberries.ru` |
| 3 | [Заказы FBS](https://dev.wildberries.ru/docs/openapi/orders-fbs) | 40 | `marketplace-api.wildberries.ru` |
| 4 | [Заказы DBW](https://dev.wildberries.ru/docs/openapi/orders-dbw) | 16 | `marketplace-api.wildberries.ru` |
| 5 | [Заказы DBS](https://dev.wildberries.ru/docs/openapi/orders-dbs) | 21 | `marketplace-api.wildberries.ru` |
| 6 | [Маркетинг и продвижение](https://dev.wildberries.ru/docs/openapi/promotion) | 39 | `advert-api.wildberries.ru` |
| 7 | [Общение с покупателями](https://dev.wildberries.ru/docs/openapi/user-communication) | 25 | `feedbacks-api.wildberries.ru`, `buyer-chat-api.wildberries.ru`, `returns-api.wildberries.ru` |
| 8 | [Тарифы](https://dev.wildberries.ru/docs/openapi/wb-tariffs) | 5 | `common-api.wildberries.ru` |
| 9 | [Заказы с самовывозом](https://dev.wildberries.ru/docs/openapi/in-store-pickup) | 18 | `marketplace-api.wildberries.ru` |
| 10 | [Поставки FBW](https://dev.wildberries.ru/docs/openapi/orders-fbw) | 7 | `supplies-api.wildberries.ru` |
| 11 | [Аналитика и данные](https://dev.wildberries.ru/docs/openapi/analytics) | 19 | `seller-analytics-api.wildberries.ru` |
| 12 | [Отчеты](https://dev.wildberries.ru/docs/openapi/reports) | 23 | `statistics-api.wildberries.ru`, `seller-analytics-api.wildberries.ru` |
| 13 | [Документы и бухгалтерия](https://dev.wildberries.ru/docs/openapi/financial-reports-and-accounting) | 11 | `finance-api.wildberries.ru`, `statistics-api.wildberries.ru`, `documents-api.wildberries.ru` |
|  | **Итого** | **286** |  |

## Что уже реализовано

- Контент: карточки товаров и справочник предметов.
- Marketplace: склады продавца, остатки FBS, новые сборочные задания и статусы.
- Аналитика/статистика: остатки FBW/FBO, исторические заказы и продажи.
- FBW: склады, заявки на поставку, товары и упаковки.
- Финансы: отчеты продаж и эквайринга с детализацией.
- Общение: вопросы, отзывы, счетчики необработанных обращений.
- Продвижение: кампании, бюджеты, платежи, расходы и полная статистика.

## Все операции

## 1. Общее (10)

Официальная страница: https://dev.wildberries.ru/docs/openapi/api-information

### Seller Information (4)

- `GET /api/common/v1/rating` — Get Seller Rating — `feedbacks-api.wildberries.ru`
- `GET /api/common/v1/subscriptions` — Get Jam Subscription Information — `common-api.wildberries.ru`
- `GET /api/common/v1/tariff-constructor/options` — Get Information about Plan Builder Options — `common-api.wildberries.ru`
- `GET /api/v1/seller-info` — Get Seller Information — `common-api.wildberries.ru`

### News API (1)

- `GET /api/communications/v2/news` — Getting Seller Portal News — `common-api.wildberries.ru`

### Seller User Management (4)

- `POST /api/v1/invite` — Create an Invitation for a New User — `user-management-api.wildberries.ru`
- `DELETE /api/v1/user` — Delete User — `user-management-api.wildberries.ru`
- `GET /api/v1/users` — Get a List of Seller Active or Invited Users — `user-management-api.wildberries.ru`
- `PUT /api/v1/users/access` — Update User's Access Permissions — `user-management-api.wildberries.ru`

### WB API Connection Check (1)

- `GET /ping` — Connection Check — `common-api.wildberries.ru`

## 2. Работа с товарами (52)

Официальная страница: https://dev.wildberries.ru/docs/openapi/work-with-products

### Categories, Subcategories, and Characteristics (10)

- `GET /api/content/v1/brands` — Brands — `content-api.wildberries.ru`
- `GET /content/v2/directory/colors` — Color — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/directory/countries` — Country of Origin — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/directory/kinds` — Gender — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/directory/seasons` — Season — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/directory/tnved` — HS-codes — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/directory/vat` — VAT Rate — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/object/all` — Subcategories List — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /content/v2/object/charcs/{subjectId}` — Subcategory Characteristics — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/object/parent/all` — Item Parent Categories — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`

### Recommendations (2)

- `POST /api/content/v1/recommendations/list` — Item Recommendations List — `content-api.wildberries.ru`
- `POST /api/content/v1/recommendations/set` — Set Item Recommendations — `content-api.wildberries.ru`

### Prices and Discounts (12)

- `POST /api/discounts-prices/v1/upload/task/b2b/wholesale` — Set Wholesale Discounts for B2B — `discounts-prices-api.wildberries.ru`
- `GET /api/v2/buffer/goods/task` — Unprocessed Upload Details — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `GET /api/v2/buffer/tasks` — Unprocessed Upload State — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `GET /api/v2/history/goods/task` — Processed Upload Details — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `GET /api/v2/history/tasks` — Processed Upload State — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `GET /api/v2/list/goods/filter` — Get Items with Prices — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `POST /api/v2/list/goods/filter` — Get Items with Prices by Item Numbers — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `GET /api/v2/list/goods/size/nm` — Get Item Sizes with Prices — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `GET /api/v2/quarantine/goods` — Get Items in Quarantine — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `POST /api/v2/upload/task` — Set Prices and Discounts — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `POST /api/v2/upload/task/club-discount` — Set WB Club Discounts — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`
- `POST /api/v2/upload/task/size` — Set Size Prices — `discounts-prices-api.wildberries.ru`, `discounts-prices-api-sandbox.wildberries.ru`

### Seller Warehouses (7)

- `GET /api/v3/dbw/warehouses/{warehouseId}/contacts` — Contacts List — `marketplace-api.wildberries.ru`
- `PUT /api/v3/dbw/warehouses/{warehouseId}/contacts` — Update Contacts List — `marketplace-api.wildberries.ru`
- `GET /api/v3/offices` — Get Offices — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/warehouses` — Get Warehouses — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/v3/warehouses` — Create Warehouse — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `DELETE /api/v3/warehouses/{warehouseId}` — Delete Warehouse — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/warehouses/{warehouseId}` — Update Warehouse — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### Seller Warehouses Inventory (3)

- `DELETE /api/v3/stocks/{warehouseId}` — Delete Inventory — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/stocks/{warehouseId}` — Get Inventory — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `PUT /api/v3/stocks/{warehouseId}` — Update Inventory — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### Listing Items (4)

- `POST /content/v2/barcodes` — Generation of SKUs — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/cards/limits` — Limits for the Listings — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/cards/upload` — List Items — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/cards/upload/add` — List Items with Merge — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`

### Listings (7)

- `POST /content/v2/cards/delete/trash` — Transfer Listing to Trash — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/cards/error/list` — Failed Listings with Errors — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/cards/moveNm` — Merging or Separating of Listings — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/cards/recover` — Recover Listing from Trash — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/cards/update` — Update Listings — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/get/cards/list` — Listings — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /content/v2/get/cards/trash` — Listings in Trash — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`

### Labels (5)

- `POST /content/v2/tag` — Create a Label — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v2/tag/nomenclature/link` — Label Management in the Listing — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `DELETE /content/v2/tag/{id}` — Delete the Label — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `PATCH /content/v2/tag/{id}` — Update the Label — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `GET /content/v2/tags` — Labels List — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`

### Media Files (2)

- `POST /content/v3/media/file` — Upload Media File — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`
- `POST /content/v3/media/save` — Upload Media Files via Links — `content-api.wildberries.ru`, `content-api-sandbox.wildberries.ru`

## 3. Заказы FBS (40)

Официальная страница: https://dev.wildberries.ru/docs/openapi/orders-fbs

### FBS Assembly Orders (10)

- `GET /api/marketplace/v3/fbs/orders/archive` — Get the List of Archived Assembly Orders — `marketplace-api.wildberries.ru`
- `GET /api/v3/orders` — Get Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/v3/orders/client` — Orders with Client Information — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/orders/new` — Get New Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/orders/status` — Get Assembly Orders Statuses — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/v3/orders/status/history` — Status History for Cross-Border Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/orders/stickers` — Get Assembly Orders Stickers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/orders/stickers/cross-border` — Get Stickers for Cross-Border Assembly Orders — `marketplace-api.wildberries.ru`
- `PATCH /api/v3/orders/{orderId}/cancel` — Cancel the Assembly Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/supplies/orders/reshipment` — Get All Assembly Orders for Re-shipment — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### Auto-return Settings (5)

- `GET /api/marketplace/v3/fbs/settings/autoreturns` — Get Auto-Return Seller Settings — `marketplace-api.wildberries.ru`
- `PATCH /api/marketplace/v3/fbs/settings/autoreturns` — Update Seller Auto-Return Settings — `marketplace-api.wildberries.ru`
- `PATCH /api/marketplace/v3/fbs/settings/autoreturns/items` — Update Item Auto-Return Settings — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/fbs/settings/autoreturns/items` — Get Item Auto-Return Settings — `marketplace-api.wildberries.ru`
- `GET /api/marketplace/v3/fbs/settings/autoreturns/subcategories/restricted` — Get Subcategories That Can't Be Returned to the Warehouse — `marketplace-api.wildberries.ru`

### FBS Label Identifiers (8)

- `POST /api/marketplace/v3/orders/meta` — Get Assembly Orders Label Identifiers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/marketplace/v3/orders/{orderId}/meta/customs-declaration` — Add Custom Declaration number to the Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `DELETE /api/v3/orders/{orderId}/meta` — Delete Assembly Order Label Identifiers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/orders/{orderId}/meta/expiration` — Add Expiration Date to the Assembly Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/orders/{orderId}/meta/gtin` — Add GTIN to the Assembly Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/orders/{orderId}/meta/imei` — Add IMEI to the Assembly Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/orders/{orderId}/meta/sgtin` — Add Labeling Code Chestny ZNAK to the Assembly Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/orders/{orderId}/meta/uin` — Add UIN (Unique Identification Number) to the Assembly Order — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### FBS Supplies (12)

- `GET /api/marketplace/v3/supplies/{supplyId}/order-ids` — Get Supply Assembly Order IDs — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PATCH /api/marketplace/v3/supplies/{supplyId}/orders` — Add Assembly Orders to the Supply — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/supplies` — Get a Supplies List — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/supplies` — Create a New Supply — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `DELETE /api/v3/supplies/{supplyId}` — Delete the Supply — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/supplies/{supplyId}` — Get Supply Details — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/supplies/{supplyId}/barcode` — Get the Supply QR Code — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PATCH /api/v3/supplies/{supplyId}/deliver` — Move the Supply to the Delivery — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `DELETE /api/v3/supplies/{supplyId}/trbx` — Delete Shipping Units from the Supply — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/supplies/{supplyId}/trbx` — Get Supply Shipping Units List — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/supplies/{supplyId}/trbx` — Add Shipping Units to the Supply — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/supplies/{supplyId}/trbx/stickers` — Get the Supply Shipping Unit QR Code Stickers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### FBS Passes (5)

- `GET /api/v3/passes` — Get Passes — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/passes` — Create Pass — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/passes/offices` — Get Offices for Pass — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `DELETE /api/v3/passes/{passId}` — Delete the Pass — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `PUT /api/v3/passes/{passId}` — Update Pass — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

## 4. Заказы DBW (16)

Официальная страница: https://dev.wildberries.ru/docs/openapi/orders-dbw

### DBW Assembly Orders (10)

- `POST /api/marketplace/v3/dbw/orders/client` — Buyer Information — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/dbw/orders/status/deliver` — Transfer Assembly Orders to Delivery — `marketplace-api.wildberries.ru`
- `GET /api/v3/dbw/orders` — Get Information on Completed Orders — `marketplace-api.wildberries.ru`
- `POST /api/v3/dbw/orders/courier` — Courier Info — `marketplace-api.wildberries.ru`
- `POST /api/v3/dbw/orders/delivery-date` — Get Delivery Date and Time — `marketplace-api.wildberries.ru`
- `GET /api/v3/dbw/orders/new` — Get New Orders — `marketplace-api.wildberries.ru`
- `POST /api/v3/dbw/orders/status` — Get Orders Statuses — `marketplace-api.wildberries.ru`
- `POST /api/v3/dbw/orders/stickers` — Get Orders Stickers — `marketplace-api.wildberries.ru`
- `PATCH /api/v3/dbw/orders/{orderId}/cancel` — Cancel the Order — `marketplace-api.wildberries.ru`
- `PATCH /api/v3/dbw/orders/{orderId}/confirm` — Transfer to Assembly — `marketplace-api.wildberries.ru`

### DBW Label Identifiers (6)

- `POST /api/marketplace/v3/dbw/orders/meta/delete` — Delete Assembly Orders Label Identifiers — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/dbw/orders/meta/details` — Get Order Label Identifiers — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/dbw/orders/meta/sgtin` — Add Labeling Codes Chestny ZNAK to Assembly Orders — `marketplace-api.wildberries.ru`
- `PUT /api/v3/dbw/orders/{orderId}/meta/gtin` — Add GTIN to the Order — `marketplace-api.wildberries.ru`
- `PUT /api/v3/dbw/orders/{orderId}/meta/imei` — Add IMEI to the Order — `marketplace-api.wildberries.ru`
- `PUT /api/v3/dbw/orders/{orderId}/meta/uin` — Add UIN (Unique Identification Number) to the Order — `marketplace-api.wildberries.ru`

## 5. Заказы DBS (21)

Официальная страница: https://dev.wildberries.ru/docs/openapi/orders-dbs

### DBS Assembly Orders (14)

- `POST /api/marketplace/v3/dbs/orders/b2b/info` — B2B Buyer Information — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/final-price` — Get Seller Prices and Amounts Charged to the Buyer — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/status/cancel` — Cancel Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/status/confirm` — Transfer to Assembly — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/status/deliver` — Transfer to Delivery — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/status/info` — Get Assembly Order Statuses — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/status/receive` — Notify that the Orders Are Received — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/status/reject` — Notify that the Orders Are Declined — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/stickers` — Get Stickers for Assembly Orders with Delivery to Pickup Point — `marketplace-api.wildberries.ru`
- `POST /api/v3/dbs/groups/info` — Get Information on Paid Delivery — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/dbs/orders` — Get Information on Completed Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/dbs/orders/client` — Buyer Information — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/dbs/orders/delivery-date` — Get Delivery Date and Time — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/dbs/orders/new` — Get New Orders List — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### DBS Label Identifiers (7)

- `POST /api/marketplace/v3/dbs/orders/meta/customs-declaration` — Add Custom Declaration to the Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/meta/delete` — Delete Assembly Orders Label Identifiers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/meta/details` — Get Assembly Orders Label Identifiers — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/meta/gtin` — Add GTIN to Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/meta/imei` — Add IMEI to Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/meta/sgtin` — Add Labeling Codes Chestny ZNAK to Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/dbs/orders/meta/uin` — Add UIN (Unique Identification Number) to Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

## 6. Маркетинг и продвижение (39)

Официальная страница: https://dev.wildberries.ru/docs/openapi/promotion

### Campaign Management (10)

- `PATCH /adv/v0/auction/nms` — Changing the Listings in Campaigns — `advert-api.wildberries.ru`
- `PUT /adv/v0/auction/placements` — Changing Placements in Campaigns with Custom Bid — `advert-api.wildberries.ru`
- `GET /adv/v0/delete` — Delete Campaign — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `GET /adv/v0/pause` — Pause Campaign — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `POST /adv/v0/rename` — Rename Campaign — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `GET /adv/v0/start` — Launch Campaign — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `GET /adv/v0/stop` — Stop Campaign — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `GET /api/advert/v0/bids/recommendations` — Recommended bids for items and search clusters — `advert-api.wildberries.ru`
- `PATCH /api/advert/v1/bids` — Changing Campaigns Bids — `advert-api.wildberries.ru`
- `GET /api/advert/v1/config` — Promotion Configuration Values — `advert-api.wildberries.ru`

### Search Clusters (7)

- `DELETE /adv/v0/normquery/bids` — Delete Bids from Search Clusters — `advert-api.wildberries.ru`
- `POST /adv/v0/normquery/bids` — Set Bids for Search Clusters — `advert-api.wildberries.ru`
- `POST /adv/v0/normquery/get-bids` — List of Search Clusters Bids — `advert-api.wildberries.ru`
- `POST /adv/v0/normquery/get-minus` — List of Campaign Minus Phrases — `advert-api.wildberries.ru`
- `POST /adv/v0/normquery/list` — Active and Inactive Search Cluster Lists — `advert-api.wildberries.ru`
- `POST /adv/v0/normquery/set-minus` — Setting and Deleting Minus Phrases — `advert-api.wildberries.ru`
- `POST /api/advert/v1/normquery/bids` — Set Bids for Search Clusters in the Currency of the Seller Account — `advert-api.wildberries.ru`

### Statistics (4)

- `POST /adv/v0/normquery/stats` — Search Clusters Statistics — `advert-api.wildberries.ru`
- `POST /adv/v1/normquery/stats` — Daily Search Clusters Statistics — `advert-api.wildberries.ru`
- `POST /adv/v1/stats` — Media Campaign Statistics — `advert-media-api.wildberries.ru`
- `GET /adv/v3/fullstats` — Campaigns Statistics — `advert-api.wildberries.ru` — **РЕАЛИЗОВАНО**

### Media (3)

- `GET /adv/v1/advert` — Information About Media Campaign — `advert-media-api.wildberries.ru`
- `GET /adv/v1/adverts` — List of Media Campaigns — `advert-media-api.wildberries.ru`
- `GET /adv/v1/count` — Media Campaigns Number — `advert-media-api.wildberries.ru`

### Finances (5)

- `GET /adv/v1/balance` — Balance — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /adv/v1/budget` — Campaign Budget — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /adv/v1/budget/deposit` — Top-up of the Campaign Budget — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `GET /adv/v1/payments` — Receiving the History of Account Top-ups — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /adv/v1/upd` — Receiving Costs History — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**

### Campaigns (2)

- `GET /adv/v1/promotion/count` — Campaigns Lists — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/advert/v2/adverts` — Campaigns Information — `advert-api.wildberries.ru` — **РЕАЛИЗОВАНО**

### Creating Campaigns (4)

- `GET /adv/v1/supplier/subjects` — Subcategories for Campaigns — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `POST /adv/v2/seacat/save-ad` — Create Campaign — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `POST /adv/v2/supplier/nms` — Listings for Campaigns — `advert-api.wildberries.ru`, `advert-api-sandbox.wildberries.ru`
- `POST /api/advert/v1/bids/min` — Minimum Bids for Listings — `advert-api.wildberries.ru`

### Promo Calendar (4)

- `GET /api/v1/calendar/promotions` — Promos List — `dp-calendar-api.wildberries.ru`
- `GET /api/v1/calendar/promotions/details` — Promos Details — `dp-calendar-api.wildberries.ru`
- `GET /api/v1/calendar/promotions/nomenclatures` — List of Items for Participating in the Promo — `dp-calendar-api.wildberries.ru`
- `POST /api/v1/calendar/promotions/upload` — Add Item to the Promo — `dp-calendar-api.wildberries.ru`

## 7. Общение с покупателями (25)

Официальная страница: https://dev.wildberries.ru/docs/openapi/user-communication

### Pinned Feedbacks (5)

- `DELETE /api/feedbacks/v1/pins` — Unpin Feedback — `feedbacks-api.wildberries.ru`
- `GET /api/feedbacks/v1/pins` — List of Pinned and Unpinned Feedbacks — `feedbacks-api.wildberries.ru`
- `POST /api/feedbacks/v1/pins` — Pin Feedbacks — `feedbacks-api.wildberries.ru`
- `GET /api/feedbacks/v1/pins/count` — Pinned and Unpinned Feedback Number — `feedbacks-api.wildberries.ru`
- `GET /api/feedbacks/v1/pins/limits` — Pinned Feedback Limits — `feedbacks-api.wildberries.ru`

### Buyers Returns (2)

- `PATCH /api/v1/claim` — Answer Buyers Application — `returns-api.wildberries.ru`
- `GET /api/v1/claims` — Buyers Return Applications — `returns-api.wildberries.ru`

### Feedbacks (8)

- `GET /api/v1/feedback` — Get the Feedback by ID — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/feedbacks` — Feedbacks List — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `PATCH /api/v1/feedbacks/answer` — Edit Response to Feedback — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `POST /api/v1/feedbacks/answer` — Reply to Feedback — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `GET /api/v1/feedbacks/archive` — List of Archived Feedbacks — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `GET /api/v1/feedbacks/count` — Number of Feedbacks — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `GET /api/v1/feedbacks/count-unanswered` — Unanswered Feedbacks — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/v1/feedbacks/order/return` — Return Item by Feedback ID — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`

### Questions (6)

- `GET /api/v1/new-feedbacks-questions` — Unseen Feedbacks and Questions — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `GET /api/v1/question` — Get the Question by ID — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/questions` — Questions List — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `PATCH /api/v1/questions` — Working with Questions — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `GET /api/v1/questions/count` — Number of Questions — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru`
- `GET /api/v1/questions/count-unanswered` — Unanswered Questions — `feedbacks-api.wildberries.ru`, `feedbacks-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**

### Buyers Chat (4)

- `GET /api/v1/seller/chats` — Chats List — `buyer-chat-api.wildberries.ru`
- `GET /api/v1/seller/download/{id}` — Get File from the Message — `buyer-chat-api.wildberries.ru`
- `GET /api/v1/seller/events` — Chat Events — `buyer-chat-api.wildberries.ru`
- `POST /api/v1/seller/message` — Send Message — `buyer-chat-api.wildberries.ru`

## 8. Тарифы (5)

Официальная страница: https://dev.wildberries.ru/docs/openapi/wb-tariffs

### Supply Rates (1)

- `GET /api/tariffs/v1/acceptance/coefficients` — Supply Rates — `common-api.wildberries.ru`

### Stock Rates (2)

- `GET /api/v1/tariffs/box` — Box Rates — `common-api.wildberries.ru`
- `GET /api/v1/tariffs/pallet` — Pallet Rates — `common-api.wildberries.ru`

### Fees (1)

- `GET /api/v1/tariffs/commission` — Item Category Fee — `common-api.wildberries.ru`

### Return Cost to Seller (1)

- `GET /api/v1/tariffs/return` — Return Rates — `common-api.wildberries.ru`

## 9. Заказы с самовывозом (18)

Официальная страница: https://dev.wildberries.ru/docs/openapi/in-store-pickup

### In-Store Pickup Assembly Orders (11)

- `POST /api/marketplace/v3/click-collect/orders/final-price` — Get seller prices and amounts charged to the buyer — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/status/cancel` — Cancel the Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/status/confirm` — Transfer to Assembly — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/status/info` — Get Assembly Order Statuses — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/status/prepare` — Notify That the Assembly Orders Are Ready for Pickup — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/status/receive` — Notify That the Orders Were Received by the Buyers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/status/reject` — Notify that the Orders Are Declined — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/click-collect/orders` — Get Information on Completed Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/click-collect/orders/client` — Buyer Information — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/v3/click-collect/orders/client/identity` — Check If the Order Belongs to the Buyer — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `GET /api/v3/click-collect/orders/new` — Get New Assembly Orders List — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

### In-Store Pickup Label Identifiers (7)

- `POST /api/marketplace/v3/click-collect/orders/meta/customs-declaration` — Add Customs Declaration Numbers to the Orders — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/meta/delete` — Delete Assembly Order Label Identifiers — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/meta/details` — Get Assembly Orders Label Identifiers — `marketplace-api.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/meta/gtin` — Add GTIN to the Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/meta/imei` — Add IMEI to the Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/meta/sgtin` — Add Labeling codes Chestny ZNAK to the Assembly Orders (Chestny ZNAK) — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`
- `POST /api/marketplace/v3/click-collect/orders/meta/uin` — Add UIN (Unique Identification Numbers) to the Assembly Orders — `marketplace-api.wildberries.ru`, `marketplace-api-sandbox.wildberries.ru`

## 10. Поставки FBW (7)

Официальная страница: https://dev.wildberries.ru/docs/openapi/orders-fbw

### Information for Forming Supplies (3)

- `POST /api/v1/acceptance/options` — Acceptance Options — `supplies-api.wildberries.ru`, `supplies-api-sandbox.wildberries.ru`
- `GET /api/v1/transit-tariffs` — Transit Directions — `supplies-api.wildberries.ru`
- `GET /api/v1/warehouses` — Warehouses List — `supplies-api.wildberries.ru`, `supplies-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**

### Supplies Information (4)

- `POST /api/v1/supplies` — Supplies List — `supplies-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/supplies/{ID}` — Supply Details — `supplies-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/supplies/{ID}/goods` — Supply Items — `supplies-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/supplies/{ID}/package` — Supply Package — `supplies-api.wildberries.ru` — **РЕАЛИЗОВАНО**

## 11. Аналитика и данные (19)

Официальная страница: https://dev.wildberries.ru/docs/openapi/analytics

### Order Feed (1)

- `POST /api/analytics/v1/order-feed` — Get Report — `seller-analytics-api.wildberries.ru`

### Stocks Report (5)

- `POST /api/analytics/v1/stocks-report/wb-warehouses` — WB Warehouses Inventory — `seller-analytics-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/v2/stocks-report/offices` — Warehouse Data — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/stocks-report/products/groups` — Group Data — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/stocks-report/products/products` — Item Data — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/stocks-report/products/sizes` — Size Data — `seller-analytics-api.wildberries.ru`

### Item Rating (1)

- `POST /api/analytics/v2/item-rating` — Get Report — `seller-analytics-api.wildberries.ru`

### Sales Funnel (3)

- `POST /api/analytics/v3/sales-funnel/grouped/history` — Grouped Listings Statistics per Days — `seller-analytics-api.wildberries.ru`
- `POST /api/analytics/v3/sales-funnel/products` — Listings Statistics per Period — `seller-analytics-api.wildberries.ru`
- `POST /api/analytics/v3/sales-funnel/products/history` — Listings Statistics per Days — `seller-analytics-api.wildberries.ru`

### Seller Analytics CSV (4)

- `GET /api/v2/nm-report/downloads` — Get the Reports List — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/nm-report/downloads` — Create the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v2/nm-report/downloads/file/{downloadId}` — Get the Report — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/nm-report/downloads/retry` — Regenerate the Report — `seller-analytics-api.wildberries.ru`

### Search Queries for Your Items (5)

- `POST /api/v2/search-report/product/orders` — Orders and Positions by Item Search Texts — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/search-report/product/search-texts` — Search Texts by Item — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/search-report/report` — Main Page — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/search-report/table/details` — Pagination by Items Within a Group — `seller-analytics-api.wildberries.ru`
- `POST /api/v2/search-report/table/groups` — Pagination by Groups — `seller-analytics-api.wildberries.ru`

## 12. Отчеты (23)

Официальная страница: https://dev.wildberries.ru/docs/openapi/reports

### Retention Reports (5)

- `GET /api/analytics/v1/deductions` — Substitutions and Incorrect Attachments — `seller-analytics-api.wildberries.ru`
- `GET /api/analytics/v1/measurement-penalties` — Logistics and Storage Costs Multiplier — `seller-analytics-api.wildberries.ru`
- `GET /api/analytics/v1/warehouse-measurements` — Warehouse Measurements — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/analytics/antifraud-details` — Self-purchases — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/analytics/goods-labeling` — Item Labeling — `seller-analytics-api.wildberries.ru`

### Acceptance Expenses (3)

- `GET /api/v1/acceptance_report` — Create the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/acceptance_report/tasks/{task_id}/download` — Get the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/acceptance_report/tasks/{task_id}/status` — Check the Status — `seller-analytics-api.wildberries.ru`

### Blocked Items (1)

- `GET /api/v1/analytics/banned-products/blocked` — Get Report — `seller-analytics-api.wildberries.ru`

### Share of Brand in Sales (3)

- `GET /api/v1/analytics/brand-share` — Get Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/analytics/brand-share/brands` — Seller Brands — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/analytics/brand-share/parent-subjects` — Parent Categories of the Brand — `seller-analytics-api.wildberries.ru`

### Report on Items with Mandatory Labeling (1)

- `POST /api/v1/analytics/excise-report` — Report on Items with Mandatory Labeling — `seller-analytics-api.wildberries.ru`

### Returns and Item Movement Report (1)

- `GET /api/v1/analytics/goods-return` — Get Report — `seller-analytics-api.wildberries.ru`

### Sales by Regions (1)

- `GET /api/v1/analytics/region-sale` — Get Report — `seller-analytics-api.wildberries.ru`

### Paid Storage (3)

- `GET /api/v1/paid_storage` — Generate the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/paid_storage/tasks/{task_id}/download` — Get the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/paid_storage/tasks/{task_id}/status` — Check the Status — `seller-analytics-api.wildberries.ru`

### Main Reports (2)

- `GET /api/v1/supplier/orders` — Orders — `statistics-api.wildberries.ru`, `statistics-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/supplier/sales` — Sales — `statistics-api.wildberries.ru`, `statistics-api-sandbox.wildberries.ru` — **РЕАЛИЗОВАНО**

### Warehouses Inventory Report (3)

- `GET /api/v1/warehouse_remains` — Create the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/warehouse_remains/tasks/{task_id}/download` — Get the Report — `seller-analytics-api.wildberries.ru`
- `GET /api/v1/warehouse_remains/tasks/{task_id}/status` — Check the Status — `seller-analytics-api.wildberries.ru`

## 13. Документы и бухгалтерия (11)

Официальная страница: https://dev.wildberries.ru/docs/openapi/financial-reports-and-accounting

### Financial Reports (6)

- `POST /api/finance/v1/acquiring/detailed` — Details for the Acquiring Expenses Reports by Period — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/finance/v1/acquiring/detailed/{reportId}` — Details for the Acquiring Expenses Reports by Report ID — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/finance/v1/acquiring/list` — Acquiring Expenses Reports List — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/finance/v1/sales-reports/detailed` — Details for the Sales Reports by Period — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/finance/v1/sales-reports/detailed/{reportId}` — Details for the Sales Reports by Report ID — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/finance/v1/sales-reports/list` — Sales Reports List — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**

### Balance (1)

- `GET /api/v1/account/balance` — Get Seller Balance — `finance-api.wildberries.ru` — **РЕАЛИЗОВАНО**

### Documents (4)

- `GET /api/v1/documents/categories` — Documents Categories — `documents-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/documents/download` — Get Document — `documents-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `POST /api/v1/documents/download/all` — Get Documents — `documents-api.wildberries.ru` — **РЕАЛИЗОВАНО**
- `GET /api/v1/documents/list` — Documents List — `documents-api.wildberries.ru` — **РЕАЛИЗОВАНО**


## Рекомендуемый порядок развития

1. **Цены и скидки:** добавить read-only сверку текущих цен и карантина; запись
   цен включать отдельным токеном и с защитой от резких изменений.
2. **Заказы FBS:** расширить текущую загрузку этикетками, поставками, пропусками,
   метаданными и безопасным управлением статусами.
3. **FBW:** дополнить текущие заявки таймслотами, коэффициентами приемки,
   документами и фактическими расхождениями.
4. **Финансовая сверка:** связать продажи, детализированный отчет реализации,
   баланс, удержания, хранение, приемку и эквайринг на уровне `srid`/`rrdId`.
5. **Аналитика:** воронка продаж, поисковые запросы, история остатков, платное
   хранение и региональная аналитика.
6. **Коммуникации:** добавить ответы на вопросы и отзывы, чаты и возвраты;
   записывающие действия отделить от сборщиков данных.
7. **Продвижение:** после стабилизации чтения добавить управление ставками и
   кампаниями с отдельными лимитами и журналом изменений.

Перед разработкой необходимо проверять конкретный метод на официальной странице:
WB публикует разные лимиты для типов токенов и переносит операции между версиями
и host-ами независимо.
