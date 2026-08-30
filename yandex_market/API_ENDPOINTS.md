# Яндекс Маркет Partner API: полный каталог методов

Документ составлен 30 августа 2026 года по официальной OpenAPI-спецификации
Яндекс Маркета, commit
[`a8941c6`](https://github.com/yandex-market/yandex-market-partner-api/commit/a8941c69a6eb6a6d58315a51157f71b4754707f8)
от 25 августа 2026 года.

В этой версии спецификации: **155 URL-путей, 165 операций, 36 функциональных
разделов**. По HTTP-методам: 113 `POST`, 35 `GET`, 15 `PUT`, 2 `DELETE`.

## Основные правила API

- Базовый URL: `https://api.partner.market.yandex.ru`.
- Авторизация: заголовок `Api-Key: <token>`. OAuth 2.0 в документации помечен
  устаревшим.
- `{businessId}` — кабинет продавца; `{campaignId}` — отдельный магазин внутри
  кабинета.
- Версия (`v1`, `v2`, `v3`) относится к конкретному методу, а не ко всему API.
  Ее нужно фиксировать в URL и обновлять отдельно для каждого метода.
- Формат данных в основном JSON; некоторые методы документов возвращают файлы.
- Таймаут со стороны API — 10 секунд; Keep-Alive не поддерживается.
- Не более 4 параллельных запросов на соответствующий кабинет или магазин.
- Максимальный размер тела запроса — 512 КБ. Частные лимиты и стоимость запроса
  указаны на странице каждого метода; состояние ресурсного лимита возвращается в
  заголовках `X-RateLimit-Resource-*`.
- Превышение лимита возвращает нестандартный HTTP-код `420 Enhance Your Calm`.
- Списочные методы используют либо `page`/`pageSize`, либо токены
  `pageToken`/`nextPageToken`; точный вариант нужно брать из схемы метода.
- Генерация отчетов асинхронная: метод `/generate` возвращает `reportId`, затем
  результат проверяется через `GET /v2/reports/info/{reportId}`.

Официальные материалы: [вызов методов](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/method-call),
[доступы Api-Key](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/access),
[лимиты](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/limits),
[ошибки](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/error-codes),
[OpenAPI](https://yandex.ru/dev/market/partner-api/doc/ru/concepts/openapi).

## Модели работы и обозначения

- `FBY` — хранение и доставка Маркетом (прежнее название FBO).
- `FBS` — хранение у продавца, доставка Маркетом.
- `DBS` — хранение и доставка продавцом.
- `Express` — экспресс-доставка.
- `LaaS` — логистика Маркета как услуга.
- **DEPRECATED** — операция уже помечена устаревшей в OpenAPI; для новой
  разработки следует выбрать указанную Маркетом замену.
- **Реализовано** — метод уже используется текущим проектом.

## Доступы Api-Key

| Доступ в кабинете | Scope в OpenAPI |
|---|---|
| Полное управление | `all-methods` |
| Просмотр всех данных | `all-methods:read-only` |
| Заказы и учет товаров | `inventory-and-order-processing` |
| Просмотр заказов и учета | `inventory-and-order-processing:read-only` |
| Управление ценами | `pricing` |
| Просмотр цен | `pricing:read-only` |
| Товары и карточки | `offers-and-cards-management` |
| Просмотр товаров и карточек | `offers-and-cards-management:read-only` |
| Продвижение | `promotion` |
| Просмотр продвижения | `promotion:read-only` |
| Финансы и отчетность | `finance-and-accounting` |
| Общение с покупателями | `communication` |
| Настройки магазинов | `settings-management` |
| Просмотр FBY-заявок | `supplies-management:read-only` |

Для каждого метода допустимо несколько scopes; точный список хранится в поле
`x-auth-scopes` официальной OpenAPI-схемы. Текущему модулю остатков достаточно
read-only-доступа к товарам и карточкам либо общего `all-methods:read-only`.

## 1. Кабинеты и магазины (4)

- `POST /v2/businesses/{businessId}/settings` — настройки кабинета
  (`FBY`, `FBS`, `DBS`, `Express`, `LaaS`).
- `GET /v2/campaigns` — список магазинов пользователя (все модели).
- `GET /v2/campaigns/{campaignId}` — информация об одном магазине (все модели).
- `GET /v2/campaigns/{campaignId}/settings` — настройки магазина (все модели).

## 2. Заказы (26)

### Основные операции (16)

- `GET /v2/campaigns/{campaignId}/orders/{orderId}` — один заказ; все модели;
  **DEPRECATED**.
- `GET /v2/campaigns/{campaignId}/orders` — заказы магазина; все модели;
  **DEPRECATED**.
- `POST /v1/businesses/{businessId}/orders` — заказы всего кабинета; все модели;
  актуальная бизнес-выборка.
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/identifiers` — передать коды
  маркировки единиц товара (`DBS`).
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/items` — удалить товар из
  заказа или уменьшить количество (`DBS`).
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/status` — изменить статус
  одного заказа (`FBS`, `DBS`, `Express`, `LaaS`).
- `POST /v2/campaigns/{campaignId}/orders/status-update` — массово изменить
  статусы (`FBS`, `DBS`, `Express`, `LaaS`).
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/delivery/shipments/{shipmentId}/boxes`
  — передать число грузовых мест (`DBS`); **DEPRECATED**.
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/cancellation/accept` — принять
  отмену покупателем (`DBS`).
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/deliverDigitalGoods` —
  передать ключи цифровых товаров (`DBS`).
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/boxes` — подготовить и
  разложить заказ по коробкам (`FBS`, `DBS`, `Express`).
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/external-id` — передать
  внешний ID (`FBS`, `DBS`, `Express`).
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/identifiers/status` — статусы
  проверки кодов маркировки (`FBS`, `Express`, `LaaS`).
- `POST /v1/campaigns/{campaignId}/orders/create` — создать заказ (`LaaS`).
- `POST /v1/campaigns/{campaignId}/orders/update` — изменить заказ (`LaaS`).
- `POST /v1/campaigns/{campaignId}/orders/update-options` — доступные интервалы
  изменения заказа (`LaaS`).

### Доставка заказа (5)

- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/delivery/date` — изменить дату
  доставки (`DBS`).
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/delivery/track` — передать
  трек-номер (`DBS`).
- `GET /v2/campaigns/{campaignId}/orders/{orderId}/buyer` — данные покупателя —
  физического лица (`DBS`).
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/verifyEac` — передать код
  подтверждения (`Express`).
- `PUT /v2/campaigns/{campaignId}/orders/{orderId}/delivery/storage-limit` —
  продлить хранение заказа (`DBS`).

### Ярлыки (3)

- `GET /v2/campaigns/{campaignId}/orders/{orderId}/delivery/shipments/{shipmentId}/boxes/{boxId}/label`
  — ярлык одной коробки (`FBS`, `DBS`, `Express`).
- `GET /v2/campaigns/{campaignId}/orders/{orderId}/delivery/labels` — ярлыки всех
  коробок заказа (`FBS`, `DBS`, `Express`).
- `GET /v2/campaigns/{campaignId}/orders/{orderId}/delivery/labels/data` — данные
  для самостоятельной печати ярлыков (`FBS`, `DBS`, `Express`).

### Покупатель-юрлицо и документы (2)

- `POST /v2/campaigns/{campaignId}/orders/{orderId}/business-buyer` — данные
  покупателя-юрлица (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/documents` — документы по
  заказу (`FBY`, `FBS`, `DBS`, `Express`).

## 3. Невыкупы и возвраты (9)

- `GET /v2/campaigns/{campaignId}/returns` — список невыкупов и возвратов (все
  модели).
- `GET /v2/campaigns/{campaignId}/orders/{orderId}/returns/{returnId}` — один
  возврат (все модели).
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/returns/{returnId}/decision`
  — принять или изменить решение (`DBS`); **DEPRECATED**.
- `POST /v2/campaigns/{campaignId}/orders/{orderId}/returns/{returnId}/decision/submit`
  — передать решение (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v1/businesses/{businessId}/returns/decisions` — получить допустимые
  решения (`FBY`, `FBS`, `DBS`, `Express`).
- `GET /v2/campaigns/{campaignId}/orders/{orderId}/returns/{returnId}/application`
  — заявление на возврат (`FBY`, `FBS`, `DBS`, `Express`).
- `GET /v2/campaigns/{campaignId}/orders/{orderId}/returns/{returnId}/decision/{itemId}/image/{imageHash}`
  — фотография товара в возврате (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v1/campaigns/{campaignId}/returns/create` — создать возврат (`LaaS`).
- `POST /v1/campaigns/{campaignId}/returns/cancel` — отменить возврат (`LaaS`).

## 4. Отгрузки FBS (12)

- `GET /v2/campaigns/{campaignId}/shipments/reception-transfer-act` — подтвердить
  ближайшую отгрузку и получить акт приема-передачи.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}` — одна
  отгрузка.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/orders/info`
  — возможность печати ярлыков.
- `POST /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/confirm` —
  подтвердить отгрузку.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/act` — акт
  приема-передачи.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/inbound-act`
  — фактический акт приема-передачи.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/transportation-waybill`
  — транспортная накладная.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/discrepancy-act`
  — акт расхождений.
- `PUT /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/pallets` —
  количество упаковок для доверительной приемки.
- `GET /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/pallet/labels`
  — ярлыки палет для доверительной приемки.
- `PUT /v2/campaigns/{campaignId}/first-mile/shipments` — найти несколько
  отгрузок.
- `POST /v2/campaigns/{campaignId}/first-mile/shipments/{shipmentId}/orders/transfer`
  — перенести заказы в следующую отгрузку.

## 5. Товары и каталог (16)

### Каталог кабинета (6)

- `POST /v2/businesses/{businessId}/offer-mappings/delete` — удалить товары из
  каталога (все модели).
- `POST /v2/businesses/{businessId}/offer-mappings` — получить товары и их
  сопоставления с карточками Маркета (все модели).
- `POST /v2/businesses/{businessId}/offer-mappings/update` — добавить или изменить
  товары (все модели).
- `POST /v2/businesses/{businessId}/offer-mappings/archive` — архивировать товары
  (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/businesses/{businessId}/offer-mappings/unarchive` — вернуть товары из
  архива (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v1/businesses/{businessId}/offer-mappings/barcodes/generate` —
  сгенерировать штрихкоды (все модели).

### Ассортимент магазинов (4)

- `POST /v2/campaigns/{campaignId}/offers` — товары конкретного магазина (все
  модели).
- `POST /v2/campaigns/{campaignId}/offers/update` — изменить условия продажи в
  магазине (все модели).
- `POST /v2/campaigns/{campaignId}/offers/delete` — удалить товары из ассортимента
  магазина (все модели).
- `POST /v2/businesses/{businessId}/offers/recommendations` — рекомендации
  Маркета по ценам (`FBY`, `FBS`, `DBS`, `Express`).

### Контент карточек (3)

- `POST /v2/category/{categoryId}/parameters` — характеристики товаров категории
  (все модели).
- `POST /v2/businesses/{businessId}/offer-cards` — заполненность карточек (все
  модели).
- `POST /v2/businesses/{businessId}/offer-cards/update` — редактировать
  категорийные характеристики (все модели).

### Скрытые предложения (3)

- `POST /v2/campaigns/{campaignId}/hidden-offers` — скрыть товары и настроить
  срок скрытия (`FBY`, `FBS`, `DBS`, `Express`).
- `GET /v2/campaigns/{campaignId}/hidden-offers` — получить скрытые товары
  (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/campaigns/{campaignId}/hidden-offers/delete` — возобновить показ
  (`FBY`, `FBS`, `DBS`, `Express`).

## 6. Остатки и оборачиваемость (4)

- `PUT /v2/campaigns/{campaignId}/offers/stocks` — передать остатки конкретного
  магазина (`FBS`, `DBS`, `Express`).
- **Реализовано:** `POST /v2/campaigns/{campaignId}/offers/stocks` — получить
  остатки и оборачиваемость (`FBY`, `FBS`, `DBS`, `Express`, `LaaS`). Именно он
  сейчас собирает остатки кампаний `149007825` и `149010920`.
- `POST /v3/businesses/{businessId}/offers/stocks/update` — передать остатки по
  партнерским складам кабинета (`FBS`, `DBS`, `Express`).
- `POST /v3/businesses/{businessId}/offers/stocks` — получить остатки по
  партнерским складам кабинета (`FBS`, `DBS`, `Express`).

Разница: `v2/campaigns/...` работает в контексте одного магазина и включает FBY;
`v3/businesses/...` агрегирует партнерские склады кабинета, но не предназначен
для FBY-складов Маркета.

Для реализованного `v2`-метода документация задает `limit` от 1 до 100 (по
умолчанию 50), пагинацию через `pageToken`/`nextPageToken` и лимит 100 000
товаров в минуту. Оборачиваемость возвращается для `FBY` и `LaaS`, только если
передать `withTurnover: true`. Для `FBS`, `DBS` и `Express` метод рекомендуется
при наличии групп складов; без групп складов Маркет рекомендует бизнес-метод
`POST /v3/businesses/{businessId}/offers/stocks`.

## 7. Цены и ценовой карантин (9)

### Цены (5)

- `POST /v2/businesses/{businessId}/offer-prices/updates` — установить цены во
  всех магазинах (все модели).
- `POST /v2/campaigns/{campaignId}/offer-prices/updates` — установить цены в одном
  магазине (все модели).
- `GET /v2/campaigns/{campaignId}/offer-prices` — список цен (`FBY`, `FBS`, `DBS`,
  `Express`); **DEPRECATED**.
- `POST /v2/campaigns/{campaignId}/offer-prices` — цены выбранных товаров в
  магазине (все модели).
- `POST /v2/businesses/{businessId}/offer-prices` — цены выбранных товаров во
  всех магазинах (все модели).

### Ценовой карантин (4)

- `POST /v2/businesses/{businessId}/price-quarantine` — карантин по кабинету.
- `POST /v2/businesses/{businessId}/price-quarantine/confirm` — подтвердить цены
  и убрать из карантина по кабинету.
- `POST /v2/campaigns/{campaignId}/price-quarantine` — карантин по магазину.
- `POST /v2/campaigns/{campaignId}/price-quarantine/confirm` — подтвердить цены
  и убрать из карантина по магазину.

Все четыре метода карантина доступны для `FBY`, `FBS`, `DBS`, `Express`.

## 8. Акции и продвижение (8)

### Акции (4)

- `POST /v2/businesses/{businessId}/promos` — список акций.
- `POST /v2/businesses/{businessId}/promos/offers` — участвующие и доступные для
  участия товары.
- `POST /v2/businesses/{businessId}/promos/offers/update` — добавить товары в
  акцию или изменить акционные цены.
- `POST /v2/businesses/{businessId}/promos/offers/delete` — удалить товары из
  акции.

### Буст продаж и ставки (4)

- `PUT /v2/businesses/{businessId}/bids` — включить буст и задать ставки по
  кабинету.
- `PUT /v2/campaigns/{campaignId}/bids` — включить буст и задать ставки по
  магазину.
- `POST /v2/businesses/{businessId}/bids/info` — получить установленные ставки.
- `POST /v2/businesses/{businessId}/bids/recommendations` — рекомендованные
  ставки.

Все восемь методов доступны для `FBY`, `FBS`, `DBS`, `Express`.

## 9. Статистика (2)

- `POST /v2/campaigns/{campaignId}/stats/orders` — детальная статистика заказов
  (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/campaigns/{campaignId}/stats/skus` — статистика по товарам (`FBY`,
  `FBS`, `DBS`, `Express`).

## 10. Отчеты и документы (27)

- `GET /v2/reports/info/{reportId}` — статус, ссылка и метаданные сформированного
  отчета или документа (все модели).
- `POST /v2/reports/united-netting/generate` — отчет по платежам (`FBY`, `FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/united-marketplace-services/generate` — стоимость услуг (все
  модели).
- `POST /v2/reports/united-orders/generate` — заказы (`FBY`, `FBS`, `DBS`,
  `Express`).
- `POST /v2/reports/united-returns/generate` — невыкупы и возвраты (все модели).
- `POST /v2/reports/goods-realization/generate` — реализация (`FBY`, `FBS`, `DBS`,
  `Express`).
- `POST /v2/reports/stocks-on-warehouses/generate` — остатки на складах (все
  модели).
- `POST /v3/businesses/{businessId}/reports/stocks/generate` — остатки на
  партнерских складах (`FBS`, `DBS`, `Express`).
- `POST /v2/reports/goods-movement/generate` — движение товаров (`FBY`, `LaaS`).
- `POST /v2/reports/shows-sales/generate` — «Аналитика продаж» (`FBY`, `FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/competitors-position/generate` — «Конкурентная позиция»
  (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/reports/goods-prices/generate` — «Цены» (`FBY`, `FBS`, `DBS`,
  `Express`).
- `POST /v2/reports/goods-turnover/generate` — оборачиваемость (`FBY`).
- `POST /v2/reports/boost-consolidated/generate` — буст продаж (`FBY`, `FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/documents/shipment-list/generate` — лист сборки (`FBS`).
- `POST /v2/reports/shelf-statistics/generate` — статистика по полкам (`FBY`,
  `FBS`, `DBS`, `Express`).
- `POST /v2/reports/documents/labels/generate` — массовые ярлыки коробок (`FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/goods-feedback/generate` — отзывы о товарах (`FBY`, `FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/shows-boost/generate` — буст показов (`FBY`, `FBS`, `DBS`,
  `Express`).
- `POST /v2/reports/banners-statistics/generate` — охватное продвижение (`FBY`,
  `FBS`, `DBS`, `Express`).
- `POST /v2/reports/closure-documents/generate` — закрывающие документы (все
  модели).
- `POST /v2/reports/jewelry-fiscal/generate` — заказы с ювелирными изделиями
  (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/reports/sales-geography/generate` — география продаж (`FBY`, `FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/key-indicators/generate` — ключевые показатели (`FBY`, `FBS`,
  `DBS`, `Express`).
- `POST /v2/reports/closure-documents/detalization/generate` — схождение с
  закрывающими документами (все модели).
- `POST /v1/businesses/{businessId}/reports/marketing-detalization/generate` —
  детализация счета маркетинга (все модели).
- `POST /v1/reports/documents/barcodes/generate` — файл со штрихкодами (`FBY`,
  `LaaS`).

## 11. Склады (6)

- `GET /v2/businesses/{businessId}/warehouses` — склады и группы складов (`FBS`,
  `DBS`, `Express`); **DEPRECATED**.
- `POST /v2/businesses/{businessId}/warehouses` — постраничный список складов
  (`FBS`, `DBS`, `Express`).
- `POST /v3/businesses/{businessId}/warehouses` — партнерские склады (`FBS`,
  `DBS`, `Express`).
- `GET /v2/warehouses` — ID фулфилмент-складов Маркета (`FBY`, `LaaS`).
- `POST /v2/campaigns/{campaignId}/warehouse/status` — изменить статус склада
  (`FBS`, `DBS`, `Express`); **DEPRECATED**.
- `POST /v3/businesses/{businessId}/warehouse/models/status` — включить или
  выключить модель работы склада (`FBS`, `DBS`, `Express`).

## 12. Точки продаж и лицензии DBS (9)

### Точки продаж (5)

- `POST /v2/campaigns/{campaignId}/outlets` — создать точку продаж.
- `GET /v2/campaigns/{campaignId}/outlets` — получить несколько точек.
- `PUT /v2/campaigns/{campaignId}/outlets/{outletId}` — изменить точку.
- `GET /v2/campaigns/{campaignId}/outlets/{outletId}` — получить одну точку.
- `DELETE /v2/campaigns/{campaignId}/outlets/{outletId}` — удалить точку.

### Лицензии точек (3)

- `GET /v2/campaigns/{campaignId}/outlets/licenses` — получить лицензии.
- `DELETE /v2/campaigns/{campaignId}/outlets/licenses` — удалить лицензии.
- `POST /v2/campaigns/{campaignId}/outlets/licenses` — создать или изменить
  лицензии.

Все восемь методов выше относятся к `DBS`.

### Логистические точки (1)

- `POST /v1/businesses/{businessId}/logistics-points` — получить пункты выдачи
  Маркета (`LaaS`).

## 13. Доставка и справочник служб (3)

- `GET /v2/delivery/services` — справочник служб доставки (`FBS`, `DBS`,
  `Express`).
- `POST /v1/campaigns/{campaignId}/delivery-options` — доступные варианты
  доставки заказа (`LaaS`).
- `POST /v1/campaigns/{campaignId}/return-delivery-options` — подходящие пункты
  выдачи для возврата (`LaaS`).

## 14. Отзывы о товарах (6)

- `POST /v2/businesses/{businessId}/goods-feedback` — отзывы о товарах продавца.
- `POST /v2/businesses/{businessId}/goods-feedback/skip-reaction` — пропустить
  реакцию на отзывы.
- `POST /v2/businesses/{businessId}/goods-feedback/comments/update` — добавить
  или изменить комментарий.
- `POST /v2/businesses/{businessId}/goods-feedback/comments/delete` — удалить
  комментарий.
- `POST /v2/businesses/{businessId}/goods-feedback/comments` — получить
  комментарии к отзыву.
- `POST /v1/businesses/{businessId}/goods-feedback-advertiser` — отзывы для
  рекламодателей.

Все методы доступны для `FBY`, `FBS`, `DBS`, `Express`.

## 15. Вопросы и ответы о товарах (3)

- `POST /v1/businesses/{businessId}/goods-questions` — вопросы покупателей.
- `POST /v1/businesses/{businessId}/goods-questions/answers` — ответы на вопрос.
- `POST /v1/businesses/{businessId}/goods-questions/update` — создать, изменить
  или удалить ответ/комментарий.

Все методы доступны для `FBY`, `FBS`, `DBS`, `Express`.

## 16. Чаты с покупателями (7)

- `POST /v2/businesses/{businessId}/chats/new` — создать чат.
- `POST /v2/businesses/{businessId}/chats` — получить доступные чаты.
- `GET /v2/businesses/{businessId}/chat` — получить чат по ID.
- `POST /v2/businesses/{businessId}/chats/file/send` — отправить файл.
- `POST /v2/businesses/{businessId}/chats/message` — отправить сообщение.
- `GET /v2/businesses/{businessId}/chats/message` — получить сообщение.
- `POST /v2/businesses/{businessId}/chats/history` — история сообщений.

Все методы доступны для `FBY`, `FBS`, `DBS`, `Express` и требуют доступа
`communication`.

## 17. Индекс качества (2)

- `POST /v2/businesses/{businessId}/ratings/quality` — индекс качества магазинов
  (`FBY`, `FBS`, `DBS`, `Express`).
- `POST /v2/campaigns/{campaignId}/ratings/quality/details` — заказы, повлиявшие
  на индекс (`FBS`, `DBS`, `Express`).

## 18. Поставки, вывоз и утилизация (3)

- `POST /v2/campaigns/{campaignId}/supply-requests` — список заявок.
- `POST /v2/campaigns/{campaignId}/supply-requests/items` — товары в заявке.
- `POST /v2/campaigns/{campaignId}/supply-requests/documents` — документы заявки.

Все методы доступны для `FBY` и `LaaS` и используют read-only scope заявок на
поставку.

## 19. Справочники (7)

### Регионы (4)

- `GET /v2/regions` — найти регионы по названию.
- `GET /v2/regions/{regionId}` — информация о регионе.
- `GET /v2/regions/{regionId}/children` — дочерние регионы.
- `POST /v2/regions/countries` — допустимые коды стран.

### Категории (2)

- `POST /v2/categories/tree` — дерево категорий.
- `POST /v2/categories/max-sale-quantum` — лимит кванта продажи и минимального
  количества в заказе; **DEPRECATED**.

### Тарифы (1)

- `POST /v2/tariffs/calculate` — калькулятор стоимости услуг (`FBY`, `FBS`, `DBS`,
  `Express`).

Региональные методы и дерево категорий доступны для всех моделей; устаревший
метод кванта — для `FBY`, `FBS`, `DBS`, `Express`.

## 20. Авторизация и операции LaaS (2)

- `POST /v2/auth/token` — узнать кабинет и доступы переданного Api-Key-токена
  (все модели).
- `POST /v1/businesses/{businessId}/operations` — статусы асинхронных операций
  (`LaaS`).

## 21. Входящие API-уведомления

Это отдельный контракт и он не входит в 165 исходящих операций Partner API:
Маркет сам вызывает настроенный продавцом HTTPS URL методом `POST /notification`.
В схеме предусмотрено 17 значений `notificationType`:

- `PING` — проверка интеграции;
- `ORDER_CREATED`, `ORDER_UPDATED`, `ORDER_STATUS_UPDATED`, `ORDER_CANCELLED` —
  события заказа;
- `ORDER_CANCELLATION_REQUEST` — заявка на отмену DBS-заказа;
- `ORDER_RETURN_CREATED`, `ORDER_RETURN_STATUS_UPDATED` — возврат или невыкуп;
- `GOODS_FEEDBACK_CREATED`, `GOODS_FEEDBACK_COMMENT_CREATED` — отзыв и
  комментарий;
- `CHAT_CREATED`, `CHAT_MESSAGE_SENT`, `CHAT_ARBITRAGE_STARTED`,
  `CHAT_ARBITRAGE_FINISHED` — чат и спор;
- `QUESTION_CREATED`, `QUESTION_ANSWER_CREATED`, `QUESTION_COMMENT_CREATED` —
  вопросы и ответы.

Обработчик должен вернуть `200` за 1 секунду для `PING` и за 10 секунд для
обычного события. Уведомления могут дублироваться, поэтому нужна идемпотентная
обработка. Маркет рекомендует проверять источник по опубликованным IP-сетям и
требует публичный HTTPS-сертификат. При технической ошибке Маркет повторяет
доставку; одна проблемная доставка блокирует последующие до успешного ответа.
Подробнее: [API-уведомления](https://yandex.ru/dev/market/partner-api/doc/ru/push-notifications/)
и [контракт `POST notification`](https://yandex.ru/dev/market/partner-api/doc/ru/push-notifications/reference/sendNotification).

## Сверка полноты

| Функциональная группа OpenAPI | Операций |
|---|---:|
| Кабинеты и магазины | 4 |
| Заказы, доставка, ярлыки и документы покупателя | 26 |
| Возвраты | 9 |
| Отгрузки | 12 |
| Каталог, ассортимент, контент, скрытые предложения | 16 |
| Остатки | 4 |
| Цены и карантин | 9 |
| Акции и ставки | 8 |
| Статистика | 2 |
| Отчеты | 27 |
| Склады | 6 |
| Точки продаж, лицензии, логистические точки | 9 |
| Доставка и службы доставки | 3 |
| Отзывы | 6 |
| Вопросы | 3 |
| Чаты | 7 |
| Индекс качества | 2 |
| Заявки на поставку | 3 |
| Справочники | 7 |
| Авторизация и операции | 2 |
| **Итого исходящих операций Partner API** | **165** |

Отдельно имеется один входящий webhook-контракт `POST /notification`, который
реализуется на стороне продавца.

## Что целесообразно добавить в этот проект

Текущий этап — получение и хранение остатков — уже закрыт. Практичный порядок
следующих модулей:

1. **Идентификация кабинета и справочники:** `auth/token`, `campaigns`, настройки
   и склады. Это позволит отказаться от части ручной конфигурации и подписывать
   строки понятными названиями магазинов и складов.
2. **Каталог:** `offer-mappings` и `campaigns/{campaignId}/offers`. Это даст
   названия, штрихкоды, Market SKU, статусы публикации и единый товарный слой для
   остатков.
3. **Заказы и продажи:** использовать актуальный бизнес-метод
   `POST /v1/businesses/{businessId}/orders` и статистику `stats/orders`; два
   старых `GET .../orders` не брать за основу нового модуля.
4. **Цены:** бизнес-метод `POST /v2/businesses/{businessId}/offer-prices` плюс
   ценовой карантин. Не использовать устаревший `GET .../offer-prices`.
5. **Финансовые и аналитические отчеты:** платежи, услуги, реализация, ключевые
   показатели. Потребуется очередь асинхронной генерации, опрос `reportId` и
   загрузка готового файла.
6. **Акции и продвижение:** сначала read-only `promos`, `promos/offers`,
   `bids/info`; методы изменения включать только после отдельной защиты от
   случайной записи.
7. **Обратная связь:** отзывы, вопросы и чаты — отдельный модуль с доступом
   `communication` и своей логикой дедупликации сообщений.

Для безопасного развития стоит держать ключ чтения отдельно от ключа с правами
изменения цен, остатков, карточек и заказов. Перечень методов нужно периодически
переснимать из официальной OpenAPI: Маркет версионирует и выводит из эксплуатации
каждую операцию независимо.
