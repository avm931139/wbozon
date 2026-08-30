# Ozon API: полный каталог методов

Документ составлен 30 августа 2026 года. Машинный каталог получен из снимков
официальных спецификаций Ozon от 19 августа 2026 года:

- Seller API: `docs.ozon.ru/api/seller/swagger.json`, 463 пути и 463 операции;
- Performance API: `docs.ozon.ru/api/performance/swagger.json`, 47 путей и 48
  операций.

Прямое автоматическое скачивание с `docs.ozon.ru` защищено антиботом. Для
воспроизводимого анализа использованы неизмененные снимки официальных Swagger из
репозитория-инструмента
[`MissiaL/ozon-api`](https://github.com/MissiaL/ozon-api/tree/1953152c36955225b459cf55963a2c3a7a234661/references),
commit `1953152` от 19 августа 2026 года. Канонический источник и описания методов
остаются на [официальном портале Ozon](https://docs.ozon.ru/api/seller/).

## Состав API

| Контур | Операций | HTTP-методы | Deprecated |
|---|---:|---|---:|
| Seller API | 463 | GET 6, POST 457 | 12 |
| Performance API | 48 | GET 22, PATCH 1, POST 24, PUT 1 | 3 |
| **Всего** | **511** |  | **15** |

Обозначения: **РЕАЛИЗОВАНО** — метод вызывается текущим кодом проекта;
**DEPRECATED** — операция помечена устаревшей в актуальной спецификации.

## Авторизация и общие правила

### Seller API

- Базовый URL: `https://api-seller.ozon.ru`.
- Стандартная авторизация: заголовки `Client-Id` и `Api-Key`; для приложений
  продавцов также предусмотрен OAuth Bearer token.
- Почти все операции используют `POST`, включая чтение данных. Если тело пустое,
  безопасно передавать `{}` с `Content-Type: application/json`.
- Это производственный API: записывающие методы меняют реальные товары, цены,
  остатки и заказы.
- Идентификаторы `offer_id`, `product_id` и `sku` обозначают разные сущности и
  не взаимозаменяемы.
- Конкретные лимиты, пагинация и допустимый период выборки заданы отдельно для
  каждого метода.

### Performance API

- Базовый URL: `https://api-performance.ozon.ru`.
- Сначала выполняется `POST /api/client/token` с `client_id`, `client_secret` и
  `grant_type=client_credentials`, далее используется `Authorization: Bearer`.
  Метод выдачи токена описан в разделе авторизации, но не включен в 48 операций
  основной OpenAPI-таблицы.
- Рекламные отчеты часто формируются асинхронно: запрос возвращает UUID, после
  чего проверяется статус и скачивается файл.
- Для ряда статистических операций документация разрешает добавить `/json` к
  пути. Проект использует варианты `/api/client/statistics/json` и
  `/api/client/statistics/daily/json`; в OpenAPI они представлены базовыми
  операциями без `/json`.

## Что уже реализовано в проекте

- Seller API: товары, общие и складские остатки, FBO/FBS-заказы, поставки,
  начисления, аналитика, отзывы и вопросы.
- Performance API: список кампаний, общая и дневная статистика.
- Миграция с отключаемых методов завершена: FBS использует
  `POST /v4/posting/fbs/list`, FBO — `POST /v3/posting/fbo/list`, отзывы —
  `POST /v2/review/list`. Старые версии остаются в каталоге только как
  `DEPRECATED` и текущим кодом не вызываются.

## Seller API — все операции (463)

### Доставка FBS (`DeliveryFBS`, 29)
- `POST /v1/assembly/carriage/posting/list` — Получить список отправлений в отгрузке
- `POST /v1/assembly/carriage/product/list` — Получить список товаров в отгрузке
- `POST /v1/assembly/fbs/posting/list` — Получить список отправлений
- `POST /v1/assembly/fbs/product/list` — Получить список товаров в отправлениях
- `POST /v1/carriage/act-discrepancy/pdf` — Получить акт о расхождениях по отгрузке FBS
- `POST /v1/carriage/approve` — Подтверждение отгрузки
- `POST /v1/carriage/cancel` — Удаление отгрузки
- `POST /v1/carriage/courier-contact/get` — Получить контактные данные продавца для курьера
- `POST /v1/carriage/courier-contact/set` — Добавить или обновить контактные данные продавца для курьера
- `POST /v1/carriage/create` — Создание отгрузки
- `POST /v1/carriage/delivery/list` — Список методов доставки и отгрузок
- `POST /v1/carriage/ettn/status` — Получить статус проверки электронной ТТН на прослеживаемой перевозке FBS
- `POST /v1/carriage/get` — Информация о перевозке
- `POST /v1/carriage/set-postings` — Изменение состава отгрузки
- `POST /v1/posting/carriage-available/list` — Список доступных перевозок
- `POST /v1/posting/fbs/product/traceable/attribute` — Получить список незаполненных атрибутов для прослеживаемых товаров
- `POST /v1/posting/fbs/split` — Разделить заказ на отправления без сборки
- `POST /v1/posting/fbs/traceable/split` — Разделить отправление с прослеживаемыми товарами
- `POST /v2/carriage/delivery/list` — Список методов доставки и отгрузок
- `POST /v2/posting/fbs/act/check-status` — Статус отгрузки и документов
- `POST /v2/posting/fbs/act/create` — Подтвердить отгрузку и создать документы
- `POST /v2/posting/fbs/act/get-barcode` — Штрихкод для отгрузки отправления
- `POST /v2/posting/fbs/act/get-barcode/text` — Значение штрихкода для отгрузки отправления
- `POST /v2/posting/fbs/act/get-container-labels` — Этикетки для грузового места
- `POST /v2/posting/fbs/act/get-pdf` — Получить PDF c документами
- `POST /v2/posting/fbs/act/get-postings` — Список отправлений в акте
- `POST /v2/posting/fbs/act/list` — Список актов по отгрузкам
- `POST /v2/posting/fbs/digital/act/check-status` — Статус формирования накладной — **DEPRECATED**
- `POST /v2/posting/fbs/digital/act/get-pdf` — Получить лист отгрузки по перевозке — **DEPRECATED**

### Создание и управление заявками на поставку FBO (`FboSupplyRequest`, 25)
- `POST /v1/cargoes-label/create` — Сгенерировать этикетки для грузомест
- `GET /v1/cargoes-label/file/{file_guid}` — Получить PDF с этикетками грузовых мест
- `POST /v1/cargoes-label/get` — Получить идентификатор этикетки для грузомест
- `POST /v1/cargoes/create` — Установка грузомест
- `POST /v1/cargoes/delete` — Удалить грузоместо в заявке на поставку
- `POST /v1/cargoes/delete/status` — Информация о статусе удаления грузоместа
- `POST /v1/cargoes/get` — Получить информацию о грузоместах
- `POST /v1/cargoes/rules/get` — Чек-лист по установке грузомест FBO
- `POST /v1/cluster/list` — Информация о кластерах и их складах
- `POST /v1/draft/crossdock/create` — Создать черновик заявки на поставку кросс-докингом
- `POST /v1/draft/direct/create` — Создать черновик заявки на прямую поставку
- `POST /v1/draft/multi-cluster/create` — Создать черновик заявки на поставку для нескольких кластеров
- `POST /v1/supply-order/cancel` — Отменить заявку на поставку
- `POST /v1/supply-order/cancel/status` — Получить статус отмены заявки на поставку
- `POST /v1/supply-order/content/update` — Редактирование товарного состава
- `POST /v1/supply-order/content/update/status` — Информация о статусе редактирования товарного состава
- `POST /v1/supply-order/content/update/validation` — Проверить новый товарный состав
- `POST /v1/warehouse/fbo/list` — Поиск точек для отгрузки поставки
- `POST /v1/warehouse/fbo/seller/list` — Получить список складов продавца
- `POST /v2/cargoes/create/info` — Получить информацию по установке грузомест
- `POST /v2/cluster/list` — Получить информацию о макролокальных кластерах
- `POST /v2/draft/create/info` — Получить информацию о черновике заявки на поставку
- `POST /v2/draft/supply/create` — Создать заявку на поставку по черновику
- `POST /v2/draft/supply/create/status` — Получить информацию о создании заявки на поставку
- `POST /v2/draft/timeslot/info` — Получить список доступных таймслотов

### Обработка заказов FBS и rFBS (`FBS`, 23)
- `POST /v1/posting/fbs/cancel-reason` — Причины отмены отправления
- `POST /v1/posting/fbs/package-label/create` — Создать задание на выгрузку этикеток
- `POST /v1/posting/fbs/package-label/get` — Получить файл с этикетками
- `POST /v1/posting/fbs/pick-up-code/verify` — Проверить код курьера
- `POST /v1/posting/fbs/restrictions` — Получить ограничения пункта приёма
- `POST /v1/posting/global/etgb` — Таможенные декларации ETGB
- `POST /v1/posting/unpaid-legal/product/list` — Список неоплаченных товаров, заказанных юридическими лицами
- `POST /v2/posting/fbs/arbitration` — Открыть спор по отправлению
- `POST /v2/posting/fbs/awaiting-delivery` — Передать отправление к отгрузке
- `POST /v2/posting/fbs/cancel` — Отменить отправление
- `POST /v2/posting/fbs/cancel-reason/list` — Причины отмены отправлений
- `POST /v2/posting/fbs/get-by-barcode` — Получить информацию об отправлении по штрихкоду
- `POST /v2/posting/fbs/package-label` — Напечатать этикетку
- `POST /v2/posting/fbs/package-label/create` — Создать задание на формирование этикеток
- `POST /v2/posting/fbs/product/cancel` — Отменить отправку некоторых товаров в отправлении
- `POST /v2/posting/fbs/product/country/list` — Список доступных стран-изготовителей
- `POST /v2/posting/fbs/product/country/set` — Добавить информацию о стране-изготовителе товара
- `POST /v3/posting/fbs/get` — Получить информацию об отправлении по идентификатору
- `POST /v3/posting/fbs/list` — Список отправлений — **DEPRECATED**
- `POST /v3/posting/fbs/unfulfilled/list` — Список необработанных отправлений — **DEPRECATED**
- `POST /v3/posting/multiboxqty/set` — Указать количество коробок для многокоробочных отправлений
- `POST /v4/posting/fbs/list` — Получить список отправлений — **РЕАЛИЗОВАНО**
- `POST /v4/posting/fbs/unfulfilled/list` — Получить список необработанных отправлений

### Загрузка и обновление товаров (`ProductAPI`, 20)
- `POST /v1/product/archive` — Перенести товар в архив
- `POST /v1/product/attributes/update` — Обновить характеристики товара
- `POST /v1/product/import-by-sku` — Создать товар по SKU
- `POST /v1/product/import/info` — Узнать статус добавления или обновления товара
- `POST /v1/product/info/description` — Получить описание товара
- `POST /v1/product/info/stocks-by-warehouse/fbo` — Получить информацию о стоках на складах FBO — **РЕАЛИЗОВАНО**
- `POST /v1/product/info/subscription` — Количество подписавшихся на товар пользователей
- `POST /v1/product/info/wrong-volume` — Список товаров с некорректными ОВХ
- `POST /v1/product/pictures/import` — Загрузить или обновить изображения товара
- `POST /v1/product/rating-by-sku` — Получить контент-рейтинг товаров по SKU
- `POST /v1/product/related-sku/get` — Получить связанные SKU
- `POST /v1/product/unarchive` — Вернуть товар из архива
- `POST /v1/product/update/offer-id` — Изменить артикулы товаров из системы продавца
- `POST /v2/product/pictures/info` — Получить изображения товаров
- `POST /v2/products/delete` — Удалить товар без SKU из архива
- `POST /v3/product/import` — Создать или обновить товар
- `POST /v3/product/info/list` — Получить информацию о товарах по идентификаторам — **РЕАЛИЗОВАНО**
- `POST /v3/product/list` — Список товаров — **РЕАЛИЗОВАНО**
- `POST /v4/product/info/attributes` — Получить описание характеристик товара
- `POST /v4/product/info/limit` — Лимиты на ассортимент, создание и обновление товаров

### Акции продавца (`SellerActions`, 18)
- `POST /v1/seller-actions/archive` — Перенести акцию в архив
- `POST /v1/seller-actions/change-activity` — Включить или выключить акцию
- `POST /v1/seller-actions/create/discount` — Создать акцию с механикой «Скидка»
- `POST /v1/seller-actions/create/discount-with-condition` — Создать акцию с механикой «Скидка от суммы заказа»
- `POST /v1/seller-actions/create/installment` — Создать акцию с механикой «Беспроцентная рассрочка»
- `POST /v1/seller-actions/create/multi-level-discount` — Создать акцию с механикой «Многоуровневая скидка от суммы»
- `POST /v1/seller-actions/create/voucher` — Создать акцию с механикой «Скидка по промокоду»
- `POST /v1/seller-actions/list` — Получить список акций
- `POST /v1/seller-actions/products/add` — Добавить товары в акцию
- `POST /v1/seller-actions/products/candidates` — Получить список доступных для акции товаров
- `POST /v1/seller-actions/products/delete` — Удалить товары из акции
- `POST /v1/seller-actions/products/list` — Получить список участвующих в акции товаров
- `POST /v1/seller-actions/update/discount` — Обновить акцию с механикой «Скидка»
- `POST /v1/seller-actions/update/discount-with-condition` — Обновить акцию с механикой «Скидка от суммы заказа»
- `POST /v1/seller-actions/update/installment` — Обновить акцию с механикой «Беспроцентная рассрочка»
- `POST /v1/seller-actions/update/multi-level-discount` — Обновить акцию с механикой «Многоуровневая скидка от суммы»
- `POST /v1/seller-actions/update/voucher` — Обновить акцию с механикой «Скидка по промокоду»
- `POST /v1/seller-actions/voucher/get` — Получить файл с промокодами в формате CSV

### Прочие методы (`BetaMethod`, 18)
- `POST /v1/analytics/manage/stocks` — Управление остатками
- `POST /v1/finance/accrual/by-day` — Получить начисления за день — **РЕАЛИЗОВАНО**
- `POST /v1/finance/accrual/postings` — Получить начисления по отправлениям
- `POST /v1/finance/accrual/types` — Получить справочник начислений
- `POST /v1/finance/balance` — Получить отчёт о балансе
- `POST /v1/posting/fbp/get` — Получить информацию об отправлении по идентификатору
- `POST /v1/product/stairway-discount/by-quantity/get` — Получить информацию о скидке от количества
- `POST /v1/product/stairway-discount/by-quantity/set` — Управлять скидкой от количества
- `POST /v1/product/visibility/info` — Получить информацию о видимости товара
- `POST /v1/product/visibility/set` — Настроить видимость товара на витрине Ozon и Ozon Селект
- `POST /v1/removal/from-stock/list` — Отчёт по вывозу и утилизации со стока FBO
- `POST /v1/removal/from-supply/list` — Отчёт по вывозу и утилизации с поставки FBO
- `POST /v1/report/realization/posting/create` — Получить позаказный отчёт о реализации товаров
- `POST /v2/actions/discounts-task/list` — Получить список заявок на скидку
- `POST /v2/posting/digital/list` — Получить список отправлений
- `POST /v2/product/certificate/create` — Создать сертификат качества
- `POST /v2/product/certification/options` — Получить параметры для создания сертификата качества
- `POST /v2/product/certification/params` — Получить обязательные параметры для создания сертификата качества

### Создание FBS-складов и управление ими (`FBSWarehouseSetup`, 17)
- `POST /v1/warehouse/fbs/create` — Создать склад
- `POST /v1/warehouse/fbs/create/drop-off/list` — Получить список drop-off пунктов для создания склада
- `POST /v1/warehouse/fbs/create/drop-off/timeslot/list` — Получить список таймслотов для создания склада с отгрузкой drop-off
- `POST /v1/warehouse/fbs/create/pick-up/timeslot/list` — Получить список таймслотов для создания склада с отгрузкой pick-up
- `POST /v1/warehouse/fbs/create/return-point/list` — Получить список пунктов возврата для создания склада
- `POST /v1/warehouse/fbs/first-mile/update` — Обновить первую милю
- `POST /v1/warehouse/fbs/pickup/courier/cancel` — Отменить вызов курьера на забор отгрузки pick-up
- `POST /v1/warehouse/fbs/pickup/courier/create` — Создать вызов курьера на забор отгрузки pick-up
- `POST /v1/warehouse/fbs/pickup/history/list` — Получить историю отгрузок курьерам
- `POST /v1/warehouse/fbs/pickup/planning/list` — Получить список складов для планирования отгрузок курьеру
- `POST /v1/warehouse/fbs/return-mile/check` — Проверить необходимость установки возвратной мили на склад
- `POST /v1/warehouse/fbs/return-mile/info` — Получить информацию о возвратной миле
- `POST /v1/warehouse/fbs/update` — Обновить склад
- `POST /v1/warehouse/fbs/update/drop-off/list` — Получить список drop-off пунктов для изменения информации склада
- `POST /v1/warehouse/fbs/update/drop-off/timeslot/list` — Получить список таймслотов для обновления склада с отгрузкой drop-off
- `POST /v1/warehouse/fbs/update/pick-up/timeslot/list` — Получить список таймслотов для обновления склада с отгрузкой pick-up
- `POST /v1/warehouse/fbs/update/return-point/list` — Получить список пунктов возврата для обновления склада

### Доставка FBO (`FBO`, 16)
- `POST /v1/posting/fbo/cancel-reason/list` — Причины отмены отправлений по схеме FBO
- `GET /v1/supplier/available_warehouses` — Загруженность складов Ozon
- `POST /v1/supply-order/bundle` — Состав поставки или заявки на поставку
- `POST /v1/supply-order/details` — Получить подробную информацию о заявке на поставку
- `POST /v1/supply-order/pass/create` — Указать данные о водителе и автомобиле
- `POST /v1/supply-order/pass/status` — Статус ввода данных о водителе и автомобиле
- `POST /v1/supply-order/status/counter` — Количество заявок по статусам
- `POST /v1/supply-order/timeslot/get` — Интервалы поставки
- `POST /v1/supply-order/timeslot/status` — Статус интервала поставки
- `POST /v1/supply-order/timeslot/update` — Обновить интервал поставки
- `POST /v2/posting/fbo/get` — Информация об отправлении
- `POST /v2/posting/fbo/list` — Список отправлений — **DEPRECATED**
- `POST /v2/supply-order/timeslot/list` — Получить список доступных интервалов поставки
- `POST /v3/posting/fbo/list` — Получить список отправлений — **РЕАЛИЗОВАНО**
- `POST /v3/supply-order/get` — Информация о заявке на поставку — **РЕАЛИЗОВАНО**
- `POST /v3/supply-order/list` — Список заявок на поставку на склад Ozon — **РЕАЛИЗОВАНО**

### Сертификаты качества (`CertificationAPI`, 15)
- `GET /v1/product/certificate/accordance-types` — Список типов соответствия требованиям (версия 1)
- `POST /v1/product/certificate/bind` — Привязать сертификат к товару
- `POST /v1/product/certificate/create` — Добавить сертификаты для товаров — **DEPRECATED**
- `POST /v1/product/certificate/delete` — Удалить сертификат
- `POST /v1/product/certificate/info` — Информация о сертификате
- `POST /v1/product/certificate/list` — Список сертификатов
- `POST /v1/product/certificate/product_status/list` — Список возможных статусов товаров
- `POST /v1/product/certificate/products/list` — Список товаров, привязанных к сертификату
- `POST /v1/product/certificate/rejection_reasons/list` — Возможные причины отклонения сертификата
- `POST /v1/product/certificate/status/list` — Возможные статусы сертификатов
- `GET /v1/product/certificate/types` — Справочник типов документов
- `POST /v1/product/certificate/unbind` — Отвязать товар от сертификата
- `POST /v1/product/certification/list` — Список сертифицируемых категорий
- `GET /v2/product/certificate/accordance-types/list` — Список типов соответствия требованиям (версия 2)
- `POST /v2/product/certification/list` — Список сертифицируемых категорий

### Работа с транспортными грузоместами FBO (`FBOTransport`, 14)
- `POST /v1/cargoes/label/transport-by-order/create` — Сгенерировать этикетки для транспортных грузомест по идентификатору поставки
- `POST /v1/cargoes/label/transport-by-order/status` — Получить статус генерации этикеток для транспортных грузомеcт по идентификатору поставки
- `POST /v1/cargoes/label/transport/create` — Сгенерировать этикетки транспортных грузомест по идентификатору грузоместа
- `POST /v1/cargoes/label/transport/status` — Получить статус генерации этикеток транспортных грузомест по идентификатору грузоместа
- `POST /v1/cargoes/supplies/get` — Получить информацию о грузоместах в поставках
- `POST /v1/cargoes/transport/activate` — Включить или отключить транспортные грузоместа в поставке
- `POST /v1/cargoes/transport/activate/status` — Получить статус включения или отключения транспортных грузомест
- `POST /v1/cargoes/transport/bind` — Связать или отвязать грузоместа и транспортные грузоместа
- `POST /v1/cargoes/transport/bind/status` — Получить статус связывания или отвязывания грузомест и транспортных грузомест
- `POST /v1/cargoes/transport/create` — Создать транспортное грузоместо
- `POST /v1/cargoes/transport/create/status` — Получить статус создания транспортного грузоместа
- `POST /v2/cargoes/delete` — Удалить грузоместа и транспортные грузоместа в заявке на поставку
- `POST /v2/cargoes/delete/status` — Получить информацию о статусе удаления грузомест и транспортных грузомест
- `POST /v2/cargoes/get` — Получить информацию о грузоместах

### Работа с грузоместами FBS (`CarriageAPI`, 13)
- `POST /v1/carriage/container/approve` — Подтвердить состав грузоместа
- `POST /v1/carriage/container/cancel` — Отменить грузоместо
- `POST /v1/carriage/container/create` — Создать грузоместо
- `POST /v1/carriage/container/document/get` — Получить документы по грузоместам — ТрН и лист отгрузки
- `POST /v1/carriage/container/fill` — Наполнить грузоместо отправлениями
- `POST /v1/carriage/container/get` — Получить информацию о грузоместах
- `POST /v1/carriage/container/label/get` — Получить этикетку по грузоместам
- `POST /v1/carriage/container/list` — Получить список грузомест
- `POST /v1/carriage/container/place-into` — Разместить коробки на палете
- `POST /v1/carriage/container/remove-from` — Убрать коробки с палеты
- `POST /v1/carriage/container/remove-postings` — Убрать отправления из грузоместа
- `POST /v1/carriage/container/status/get` — Получить статус грузомест FBS
- `POST /v1/carriage/container/task/info` — Получить статус задачи грузового места

### Работа с отзывами (`ReviewAPI`, 12)
- `POST /v1/review/change-status` — Изменить статус отзывов — **DEPRECATED**
- `POST /v1/review/comment/create` — Оставить комментарий на отзыв
- `POST /v1/review/comment/delete` — Удалить комментарий на отзыв — **DEPRECATED**
- `POST /v1/review/comment/list` — Получить список комментариев на отзыв
- `POST /v1/review/count` — Количество отзывов по статусам — **DEPRECATED**
- `POST /v1/review/info` — Получить информацию об отзыве — **DEPRECATED**
- `POST /v1/review/list` — Получить список отзывов — **DEPRECATED**
- `POST /v2/review/change-status` — Изменить статус отзывов
- `POST /v2/review/comment/delete` — Удалить комментарий на отзыв
- `POST /v2/review/count` — Получить количество отзывов по статусам
- `POST /v2/review/info` — Получить информацию по отзыву
- `POST /v2/review/list` — Получить список отзывов — **РЕАЛИЗОВАНО**

### Стратегии ценообразования (`PricingStrategyAPI`, 12)
- `POST /v1/pricing-strategy/competitors/list` — Список конкурентов
- `POST /v1/pricing-strategy/create` — Создать стратегию
- `POST /v1/pricing-strategy/delete` — Удалить стратегию
- `POST /v1/pricing-strategy/info` — Информация о стратегии
- `POST /v1/pricing-strategy/list` — Список стратегий
- `POST /v1/pricing-strategy/product/info` — Цена товара у конкурента
- `POST /v1/pricing-strategy/products/add` — Добавить товары в стратегию
- `POST /v1/pricing-strategy/products/delete` — Удалить товары из стратегии
- `POST /v1/pricing-strategy/products/list` — Список товаров в стратегии
- `POST /v1/pricing-strategy/status` — Изменить статус стратегии
- `POST /v1/pricing-strategy/strategy-ids-by-product-ids` — Список идентификаторов стратегий
- `POST /v1/pricing-strategy/update` — Обновить стратегию

### Отчёты (`ReportAPI`, 11)
- `POST /v1/finance/cash-flow-statement/list` — Финансовый отчёт
- `POST /v1/report/discounted/create` — Отчёт об уценённых товарах
- `POST /v1/report/info` — Информация об отчёте
- `POST /v1/report/list` — Список отчётов
- `POST /v1/report/marked-products-sales/create` — Сгенерировать отчёт по продажам товаров с маркировкой
- `POST /v1/report/placement/by-products/create` — Получить отчёт о стоимости размещения по товарам
- `POST /v1/report/placement/by-supplies/create` — Получить отчёт о стоимости размещения по поставкам
- `POST /v1/report/postings/create` — Отчёт об отправлениях
- `POST /v1/report/products/create` — Отчёт по товарам
- `POST /v1/report/warehouse/stock` — Отчёт об остатках на FBS-складе
- `POST /v2/report/returns/create` — Отчёт о возвратах

### Работа с созданной поставкой FBP (`DeliveryFBP`, 11)
- `POST /v1/fbp/act-from/create` — Сгенерировать акт приёмки
- `POST /v1/fbp/act-from/get` — Получить статус генерации акта приёмки
- `POST /v1/fbp/act-to/create` — Сгенерировать транспортную накладную
- `POST /v1/fbp/act-to/get` — Получить статус генерации транспортной накладной
- `POST /v1/fbp/archive/get` — Получить информацию о завершённой поставке
- `POST /v1/fbp/archive/list` — Получить список завершённых поставок
- `POST /v1/fbp/label/create` — Cоздать задание на генерацию этикеток
- `POST /v1/fbp/label/get` — Получить статус задания на генерацию этикеток
- `POST /v1/fbp/order/get` — Получить информацию о конкретной поставке
- `POST /v1/fbp/order/list` — Получить список поставок
- `POST /v1/posting/fbp/list` — Получить список отправлений

### Цены и остатки товаров (`Prices&StocksAPI`, 11)
- `POST /v1/product/action/timer/status` — Получить статус установленного таймера
- `POST /v1/product/action/timer/update` — Обновление таймера актуальности минимальной цены
- `POST /v1/product/import/prices` — Обновить цену
- `POST /v1/product/info/discounted` — Узнать информацию об уценке и основном товаре по SKU уценённого товара
- `POST /v1/product/info/stocks-by-warehouse/fbs` — Информация об остатках на складах продавца (FBS и rFBS)
- `POST /v1/product/info/warehouse/stocks` — Получить информацию по остаткам на складе FBS и rFBS
- `POST /v1/product/update/discount` — Установить скидку на уценённый товар
- `POST /v2/product/info/stocks-by-warehouse/fbs` — Получить информацию об остатках на складах продавца — **РЕАЛИЗОВАНО**
- `POST /v2/products/stocks` — Обновить количество товаров на складах
- `POST /v4/product/info/stocks` — Информация о количестве товаров — **РЕАЛИЗОВАНО**
- `POST /v5/product/info/prices` — Получить информацию о цене товара

### Premium-методы (`Premium`, 10)
- `POST /v1/analytics/data` — Данные аналитики — **РЕАЛИЗОВАНО**
- `POST /v1/analytics/product-queries` — Получить информацию о запросах моих товаров
- `POST /v1/analytics/product-queries/details` — Получить детализацию запросов по товару
- `POST /v1/chat/send/message` — Отправить сообщение
- `POST /v1/chat/start` — Создать новый чат
- `POST /v1/finance/realization/by-day` — Отчёт о реализации товаров за день
- `POST /v1/product/prices/details` — Получить подробную информацию о ценах товаров
- `POST /v1/search-queries/text` — Получить список поисковых запросов по тексту
- `POST /v1/search-queries/top` — Получить список популярных поисковых запросов
- `POST /v2/chat/read` — Отметить сообщения как прочитанные

### Работа с FBP-черновиками с доставкой direct (`DraftDirectFBP`, 10)
- `POST /v1/fbp/draft/direct/create` — Создать черновик заявки на поставку без указания способа доставки
- `POST /v1/fbp/draft/direct/delete` — Удалить черновик заявки на поставку
- `POST /v1/fbp/draft/direct/product/validate` — Проверить список товаров для склада партнёра
- `POST /v1/fbp/draft/direct/registrate` — Перевести черновик в действующую поставку
- `POST /v1/fbp/draft/direct/seller-dlv/create` — Создать черновик с доставкой силами продавца
- `POST /v1/fbp/draft/direct/seller-dlv/edit` — Обновить информацию о доставке силами продавца в черновике
- `POST /v1/fbp/draft/direct/timeslot/edit` — Отредактировать таймслот в черновике
- `POST /v1/fbp/draft/direct/timeslot/get` — Получить список таймслотов для прямой поставки
- `POST /v1/fbp/draft/direct/tpl-dlv/create` — Создать черновик заявки на доставку сторонней транспортной компанией
- `POST /v1/fbp/draft/direct/tpl-dlv/edit` — Редактировать черновик поставки со способом доставки сторонней транспортной компанией

### Работа со складами FBS и rFBS (`WarehouseAPI`, 10)
- `POST /v1/delivery-method/list` — Список методов доставки склада
- `POST /v1/delivery-method/return/settings/get` — Получить информацию по возвратным настройкам rFBS и rFBS Express
- `POST /v1/warehouse/archive` — Перенести склад в архив
- `POST /v1/warehouse/invalid-products/get` — Получить список товаров с ограничениями по доставке
- `POST /v1/warehouse/list` — Список складов
- `POST /v1/warehouse/operation/status` — Получить статус операции
- `POST /v1/warehouse/unarchive` — Перенести склад из архива
- `POST /v1/warehouse/warehouses-with-invalid-products` — Получить список складов с ограниченными для доставки товарами
- `POST /v2/delivery-method/list` — Список методов доставки realFBS-склада
- `POST /v2/warehouse/list` — Список складов

### Финансовые отчёты (`FinanceAPI`, 10)
- `POST /v1/finance/compensation` — Отчёт о компенсациях
- `POST /v1/finance/decompensation` — Отчёт о декомпенсациях
- `POST /v1/finance/document-b2b-sales` — Реестр продаж юридическим лицам
- `POST /v1/finance/document-b2b-sales/json` — Реестр продаж юридическим лицам в JSON-формате
- `POST /v1/finance/mutual-settlement` — Отчёт о взаиморасчётах
- `POST /v1/finance/products/buyout` — Отчёт о выкупленных товарах
- `POST /v1/finance/realization/posting` — Позаказный отчёт о реализации товаров
- `POST /v2/finance/realization` — Отчёт о реализации товаров (версия 2)
- `POST /v3/finance/transaction/list` — Список транзакций
- `POST /v3/finance/transaction/totals` — Суммы транзакций

### Акции Ozon (`Promos`, 8)
- `GET /v1/actions` — Список акций
- `POST /v1/actions/candidates` — Список доступных для акции товаров
- `POST /v1/actions/discounts-task/approve` — Согласовать заявку на скидку
- `POST /v1/actions/discounts-task/decline` — Отклонить заявку на скидку
- `POST /v1/actions/discounts-task/list` — Список заявок на скидку
- `POST /v1/actions/products` — Список участвующих в акции товаров
- `POST /v1/actions/products/activate` — Добавить товар в акцию
- `POST /v1/actions/products/deactivate` — Удалить товары из акции

### Возвратные отгрузки (`ReturnAPI`, 8)
- `POST /v1/return/giveout/barcode` — Значение штрихкода для возвратных отгрузок
- `POST /v1/return/giveout/barcode-reset` — Сгенерировать новый штрихкод
- `POST /v1/return/giveout/get-pdf` — Штрихкод для получения возвратной отгрузки в формате PDF
- `POST /v1/return/giveout/get-png` — Штрихкод для получения возвратной отгрузки в формате PNG
- `POST /v1/return/giveout/info` — Информация о возвратной отгрузке
- `POST /v1/return/giveout/is-enabled` — Проверить возможность получения возвратных отгрузок по штрихкоду
- `POST /v1/return/giveout/list` — Список возвратных отгрузок
- `POST /v1/returns/company/fbs/info` — Количество возвратов FBS

### Работа с FBP-черновиками c доставкой drop-off (`DraftDropOffFBP`, 8)
- `POST /v1/fbp/draft/drop-off/create` — Создать черновик для доставки в drop-off пункт
- `POST /v1/fbp/draft/drop-off/delete` — Удалить черновик для доставки в drop-off пункт
- `POST /v1/fbp/draft/drop-off/dlv/edit` — Отредактировать детали доставки для drop-off черновика
- `POST /v1/fbp/draft/drop-off/point/list` — Получить список drop-off пунктов в провинции
- `POST /v1/fbp/draft/drop-off/point/timetable` — Получить расписание работы drop-off пункта
- `POST /v1/fbp/draft/drop-off/product/validate` — Проверить список товаров, которые склад партнёра может принять
- `POST /v1/fbp/draft/drop-off/province/list` — Получить список провинций
- `POST /v1/fbp/draft/drop-off/registrate` — Перевести черновик в действующую поставку

### Работа с вопросами и ответами (`Questions&Answers`, 8)
- `POST /v1/question/answer/create` — Создать ответ на вопрос
- `POST /v1/question/answer/delete` — Удалить ответ на вопрос
- `POST /v1/question/answer/list` — Список ответов на вопрос
- `POST /v1/question/change-status` — Изменить статус вопросов
- `POST /v1/question/count` — Количество вопросов по статусам
- `POST /v1/question/info` — Информация о вопросе
- `POST /v1/question/list` — Список вопросов — **РЕАЛИЗОВАНО**
- `POST /v1/question/top-sku` — Товары с наибольшим количеством вопросов

### Доставка rFBS (`DeliveryrFBS`, 7)
- `POST /v1/posting/cutoff/set` — Уточнить дату отгрузки отправления
- `POST /v1/posting/fbs/timeslot/change-restrictions` — Доступные даты для переноса доставки
- `POST /v1/posting/fbs/timeslot/set` — Перенести дату доставки
- `POST /v2/fbs/posting/delivered` — Изменить статус на «Доставлено»
- `POST /v2/fbs/posting/delivering` — Изменить статус на «Доставляется»
- `POST /v2/fbs/posting/last-mile` — Изменить статус на «Последняя миля»
- `POST /v2/fbs/posting/tracking-number/set` — Добавить трек-номера

### Полигоны (`PolygonAPI`, 7)
- `POST /v1/polygon/bind` — Свяжите метод доставки с полигоном доставки
- `POST /v1/polygon/create` — Создайте полигон доставки
- `POST /v1/polygon/delete` — Удалить полигон из области доставки
- `POST /v1/polygon/list` — Получить список установленных полигонов на метод доставки
- `POST /v1/polygon/time/coordinates/update` — Обновить координаты полигона доставки
- `POST /v1/polygon/time/set` — Установить новое время доставки в полигоне
- `POST /v2/polygon/bind` — Связать метод доставки с полигоном

### Пропуски (`Pass`, 7)
- `POST /v1/carriage/pass/create` — Создать пропуск
- `POST /v1/carriage/pass/delete` — Удалить пропуск
- `POST /v1/carriage/pass/update` — Обновить пропуск
- `POST /v1/pass/list` — Список пропусков
- `POST /v1/return/pass/create` — Создать пропуск для возврата
- `POST /v1/return/pass/delete` — Удалить пропуск для возврата
- `POST /v1/return/pass/update` — Обновить пропуск для возврата

### Работа с пуш-уведомлениями (`Notification`, 7)
- `POST /v1/notification/check` — Проверить URL-адрес для уведомлений
- `POST /v1/notification/delete` — Удалить URL-адрес для уведомлений
- `POST /v1/notification/enable` — Включить или выключить уведомления на URL-адрес
- `POST /v1/notification/list` — Получить информацию по подключённым URL-адресам
- `POST /v1/notification/push-type/list` — Получить типы пуш-уведомлений
- `POST /v1/notification/set` — Подключить URL-адрес для уведомлений
- `POST /v1/notification/update` — Изменить URL-адрес для уведомлений

### Создание складов rFBS Express и управление ими (`rFBSWarehouseSetup`, 7)
- `POST /v1/warehouse/erfbs/aggregator/create` — Создать склад с методом доставки «Партнёры Ozon»
- `POST /v1/warehouse/erfbs/aggregator/delivery-method/update` — Обновить метод доставки «Партнёры Ozon»
- `POST /v1/warehouse/erfbs/non-integrated/create` — Создать склад с методом доставки «Вы или сторонняя служба»
- `POST /v1/warehouse/erfbs/non-integrated/delivery-method/update` — Обновить метод доставки «Вы или сторонняя служба»
- `POST /v1/warehouse/erfbs/update` — Обновить склад
- `POST /v1/warehouse/rfbs/pause` — Поставить rFBS-склад на паузу
- `POST /v1/warehouse/rfbs/unpause` — Снять rFBS-склад с паузы

### Управление кодами маркировки и сборкой заказов для FBS/rFBS (`FBS&rFBSMarks`, 7)
- `POST /v1/fbs/posting/product/exemplar/update` — Обновить данные экземпляров
- `POST /v4/posting/fbs/ship` — Собрать заказ (версия 4)
- `POST /v4/posting/fbs/ship/package` — Частичная сборка отправления (версия 4)
- `POST /v5/fbs/posting/product/exemplar/status` — Получить статус добавления экземпляров
- `POST /v5/fbs/posting/product/exemplar/validate` — Валидация кодов маркировки
- `POST /v6/fbs/posting/product/exemplar/create-or-get` — Получить данные созданных экземпляров
- `POST /v6/fbs/posting/product/exemplar/set` — Проверить и сохранить данные экземпляров

### Атрибуты и характеристики Ozon (`CategoryAPI`, 5)
- `POST /v1/description-category/attribute` — Список характеристик категории
- `POST /v1/description-category/attribute/values` — Справочник значений характеристики
- `POST /v1/description-category/attribute/values/search` — Поиск по справочным значениям характеристики
- `POST /v1/description-category/tree` — Дерево категорий и типов товаров
- `POST /v1/product/placement-zone/info` — Получить зоны размещения товаров по SKU перед поставкой

### Доставка (`DeliveryAPI`, 5)
- `POST /v1/delivery/check` — Проверить доступность доставки для покупателя
- `POST /v1/delivery/map` — Отрисовать точки на карте
- `POST /v1/delivery/point/info` — Получить информацию о точке самовывоза
- `POST /v1/delivery/point/list` — Получить список точек самовывоза
- `POST /v2/delivery/checkout` — Получить доступные варианты доставки

### Работа с FBP-черновиками с доставкой pick-up (`DraftPickupFBP`, 5)
- `POST /v1/fbp/draft/pick-up/create` — Создать черновик заявки на pick-up поставку
- `POST /v1/fbp/draft/pick-up/delete` — Отменить черновик заявки на pick-up поставку
- `POST /v1/fbp/draft/pick-up/dlv/edit` — Изменить черновик заявки на pick-up поставку
- `POST /v1/fbp/draft/pick-up/product/validate` — Провалидировать список товаров для pick-up поставки
- `POST /v1/fbp/draft/pick-up/registrate` — Перевести черновик в действующую поставку

### Акции Ozon (`PromosBeta`, 4)
- `POST /v1/actions/auto-add/products/candidates` — Получить список доступных товаров для автодобавления в акцию
- `POST /v1/actions/auto-add/products/delete` — Удалить товары из автодобавления в акцию
- `POST /v1/actions/auto-add/products/list` — Получить список товаров из автодобавления в акцию
- `POST /v1/actions/auto-add/products/update` — Добавить или обновить товары в автодобавлении в акцию

### Возвраты товаров FBO и FBS (`ReturnsAPI`, 4)
- `POST /v1/returns/list` — Информация о возвратах FBO и FBS
- `POST /v1/returns/settings/utilization/history` — Получить историю изменений автоутилизации
- `POST /v1/returns/settings/utilization/info` — Получить настройки автоутилизации
- `POST /v1/returns/settings/utilization/update` — Обновить настройки автоутилизации

### Заказы (`OrderAPI`, 4)
- `POST /v1/order/cancel` — Отменить заказ
- `POST /v1/order/cancel/check` — Проверить возможность отмены заказа
- `POST /v1/order/cancel/status` — Получить статус отмены заказа
- `POST /v2/order/create` — Создать заказ

### Накладные (`SupplierAPI`, 4)
- `POST /v1/invoice/delete` — Удалить ссылку на счёт-фактуру
- `POST /v1/invoice/file/upload` — Загрузка счёта-фактуры
- `POST /v2/invoice/create-or-update` — Создать или изменить счёт-фактуру
- `POST /v2/invoice/get` — Получить информацию о счёте-фактуре

### Работа с FBP-поставками с доставкой direct (`OrderDirectFBP`, 4)
- `POST /v1/fbp/order/direct/cancel` — Отменить поставку
- `POST /v1/fbp/order/direct/seller-dlv/edit` — Обновить информацию о доставке силами продавца
- `POST /v1/fbp/order/direct/timeslot/edit` — Отредактировать таймслот в заявке на поставку
- `POST /v1/fbp/order/direct/timeslot/list` — Получить список таймслотов для поставки

### Работа с актами FBO (`SupplyOrderAPI`, 4)
- `POST /v1/supply-order/act/accept` — Согласовать акт
- `POST /v1/supply-order/act/accept/status` — Получить статус согласования акта
- `POST /v1/supply-order/act/product/get` — Получить информацию о товарах в акте
- `POST /v1/supply-order/act/summary/get` — Получить информацию об акте

### Рейтинг продавца (`SellerRating`, 4)
- `POST /v1/rating/history` — Получить информацию о рейтингах продавца за период
- `POST /v1/rating/index/fbs/info` — Получить индекс ошибок FBS и rFBS
- `POST /v1/rating/index/fbs/posting/list` — Список отправлений, которые повлияли на индекс ошибок FBS и rFBS
- `POST /v1/rating/summary` — Получить информацию о текущих рейтингах продавца

### Аналитические отчёты (`AnalyticsAPI`, 3)
- `POST /v1/analytics/stocks` — Получить аналитику по остаткам — **РЕАЛИЗОВАНО**
- `POST /v1/analytics/turnover/stocks` — Оборачиваемость товара
- `POST /v2/analytics/stock_on_warehouses` — Отчёт по остаткам и товарам — **РЕАЛИЗОВАНО**

### Возвраты товаров rFBS (`RFBSReturnsAPI`, 3)
- `POST /v1/returns/rfbs/action/set` — Передать доступные действия для rFBS возвратов
- `POST /v2/returns/rfbs/get` — Информация о заявке на возврат
- `POST /v2/returns/rfbs/list` — Список заявок на возврат

### Отмены заказов (`CancellationAPI`, 3)
- `POST /v2/conditional-cancellation/approve` — Подтвердить заявку на отмену rFBS
- `POST /v2/conditional-cancellation/list` — Получить список заявок на отмену rFBS
- `POST /v2/conditional-cancellation/reject` — Отклонить заявку на отмену rFBS

### Отправления (`FboPostingAPI`, 3)
- `POST /v1/posting/cancel` — Отменить отправление из заказа
- `POST /v1/posting/cancel/status` — Проверить статус отмены отправления
- `POST /v1/posting/marks` — Получить маркировки экземпляров из отправления

### Причины отмены (`CancelReasonAPI`, 3)
- `POST /v1/cancel-reason/list` — Причины отмены отправлений
- `POST /v1/cancel-reason/list-by-order` — Причины отмены заказа
- `POST /v1/cancel-reason/list-by-posting` — Причины отмены отправления

### Работа с FBP-поставками с доставкой drop-off (`OrderDropOffFBP`, 3)
- `POST /v1/fbp/order/drop-off/cancel` — Отменить поставку drop-off
- `POST /v1/fbp/order/drop-off/dlv/edit` — Отредактировать информацию о поставке на drop-off пункт
- `POST /v1/fbp/order/drop-off/timetable` — Получить график работы drop-off пункта

### Работа с FBP-черновиками (`DeliveryFBPDraft`, 3)
- `POST /v1/fbp/draft/get` — Получить информацию о черновике поставки
- `POST /v1/fbp/draft/list` — Список черновиков поставки
- `POST /v1/fbp/warehouse/list` — Получить список партнёрских складов

### Работа с цифровыми товарами (`Digital`, 3)
- `POST /v1/posting/digital/codes/upload` — Загрузить коды цифровых товаров для отправления
- `POST /v1/posting/digital/list` — Получить список отправлений — **DEPRECATED**
- `POST /v1/product/digital/stocks/import` — Обновить количество цифровых товаров

### Чаты с покупателями (`ChatAPI`, 3)
- `POST /v1/chat/send/file` — Отправить файл
- `POST /v3/chat/history` — История чата
- `POST /v3/chat/list` — Список чатов

### Чеки (`Receipt`, 3)
- `POST /v1/receipts/get` — Получить чек в формате PDF
- `POST /v1/receipts/seller/list` — Получить список чеков продавца
- `POST /v1/receipts/upload` — Загрузить чек

### Информация по кабинету продавца (`SellerInfo`, 2)
- `POST /v1/seller/info` — Информация о кабинете продавца
- `POST /v1/seller/ozon-logistics/info` — Информация о подключении Ozon Доставки

### Работа с FBP-поставками с доставкой pick-up (`OrderPickupFBP`, 2)
- `POST /v1/fbp/order/pick-up/cancel` — Отменить pick-up поставку
- `POST /v1/fbp/order/pick-up/dlv/edit` — Изменить данные о точке забора

### Работа с квантами (`Quants`, 2)
- `POST /v1/product/quant/info` — Информация об эконом-товаре
- `POST /v1/product/quant/list` — Список эконом-товаров

### Штрихкоды товаров (`BarcodeAPI`, 2)
- `POST /v1/barcode/add` — Привязать штрихкод к товару
- `POST /v1/barcode/generate` — Создать штрихкод для товара

### Информация по API-ключу (`APIkey`, 1)
- `POST /v1/roles` — Получить список ролей и методов по API-ключу

### Сертификаты брендов (`BrandAPI`, 1)
- `POST /v1/brand/company-certification/list` — Список сертифицируемых брендов

### Склады FBO (`FBOWarehouse`, 1)
- `POST /v1/warehouse/ozon/list` — Получить список складов Ozon


## Performance API — все операции (48)

### Статистика (`Statistics`, 17)
- `POST /api/client/statistic/orders/generate` — Получить отчёт по заказам в оплате за заказ — выбранные товары
- `POST /api/client/statistic/products/generate` — Получить отчёт по товарам в оплате за заказ — выбранные товары
- `POST /api/client/statistics` — Статистика по кампании — **РЕАЛИЗОВАНО**
- `GET /api/client/statistics/all_sku_promo/orders/generate` — Получить отчёт по заказам в оплате за заказ — все товары
- `GET /api/client/statistics/all_sku_promo/products/generate` — Получить отчёт по товарам в оплате за заказ — все товары
- `POST /api/client/statistics/attribution` — Отчёт по заказам
- `GET /api/client/statistics/campaign/media` — Статистика по медийным кампаниям
- `GET /api/client/statistics/campaign/product` — Статистика по кампании Оплата за клик
- `GET /api/client/statistics/daily` — Дневная статистика по кампаниям — **РЕАЛИЗОВАНО**
- `GET /api/client/statistics/expense` — Статистика по расходу кампаний
- `GET /api/client/statistics/externallist` — Список отчётов, сгенерированных через API
- `GET /api/client/statistics/list` — Список отчётов, сгенерированных через интерфейс
- `POST /api/client/statistics/phrases` — Отчёт по поисковым запросам
- `POST /api/client/statistics/products/sku` — Получить статистику по товарам в оплате за клик
- `GET /api/client/statistics/report` — Получить отчёты
- `POST /api/client/statistics/video` — Статистика по показам видеобаннера
- `GET /api/client/statistics/{UUID}` — Cтатус отчёта

### Оплата за заказ (`Search-Promo`, 12)
- `GET /api/client/campaign/all_sku_promo/activate` — Включить продвижение в оплате за заказ — все товары
- `GET /api/client/campaign/all_sku_promo/deactivate` — Выключить продвижение в оплате за заказ — все товары
- `GET /api/client/campaign/all_sku_promo/set_bid` — Установить ставку для продвижения в Оплате за заказ — все товары
- `POST /api/client/campaign/search_promo/carrots/disable` — Отключить продвижение товаров в акции «Морковск»
- `POST /api/client/campaign/search_promo/carrots/enable` — Включить продвижение товаров в акции «Морковск»
- `POST /api/client/campaign/search_promo/v2/bids/delete` — Удалить товар из продвижения в оплате за заказ
- `POST /api/client/campaign/search_promo/v2/bids/set` — Установить ставку на товар — **DEPRECATED**
- `POST /api/client/campaign/search_promo/v2/products` — Список товаров в продвижении в оплате за заказ
- `POST /api/client/search_promo/bids/recommendation` — Рекомендованные ставки для товаров — **DEPRECATED**
- `POST /api/client/search_promo/get_cpo_min_bids` — Получить фиксированные ставки для товаров
- `POST /api/client/search_promo/product/disable` — Отключить продвижение товара в оплате за заказ
- `POST /api/client/search_promo/product/enable` — Включить продвижение товара в оплате за заказ

### Кампании и рекламируемые объекты (`Campaign`, 5)
- `GET /api/client/campaign` — Список кампаний — **РЕАЛИЗОВАНО**
- `GET /api/client/campaign/{campaignId}/objects` — Список продвигаемых объектов в кампании
- `GET /api/client/limits/list` — Лимиты ставок для инструментов продвижения
- `POST /api/client/min/sku` — Минимальная ставка для товаров по SKU
- `GET /api/client/products_with_bonuses` — Список товаров с бонусами

### Оплата за клик (`Ad`, 5)
- `POST /api/client/campaign/cpc/v2/product` — Создать кампанию с оплатой за клики
- `PATCH /api/client/campaign/{campaignId}` — Параметры кампании
- `POST /api/client/campaign/{campaignId}/activate` — Активировать кампанию
- `POST /api/client/campaign/{campaignId}/deactivate` — Выключить кампанию
- `POST /external/api/dynamic_budget` — Рассчитать минимальный бюджет кампании — **DEPRECATED**

### Товары в Оплате за клик (`Product`, 5)
- `POST /api/client/campaign/{campaignId}/products` — Добавить товары в кампанию
- `PUT /api/client/campaign/{campaignId}/products` — Обновить ставки товаров
- `GET /api/client/campaign/{campaignId}/products/bids/competitive` — Конкурентные ставки для товара
- `POST /api/client/campaign/{campaignId}/products/delete` — Удалить товары из кампании
- `GET /api/client/campaign/{campaignId}/v2/products` — Список товаров кампании

### Аналитика внешнего трафика (`Vendor`, 4)
- `GET /api/client/organisation/vendor_tag` — Метка организации для внешних рекламных кампаний
- `POST /api/client/vendors/statistics` — Отчёт с аналитикой внешнего трафика
- `GET /api/client/vendors/statistics/list` — Список запрошенных отчётов с аналитикой внешнего трафика
- `GET /api/client/vendors/statistics/{UUID}` — Информация об отчёте по UUID


## Рекомендуемый порядок развития

1. **Необработанные FBS-отправления:** дополнить уже выполненную миграцию методом
   `POST /v4/posting/fbs/unfulfilled/list` для оперативной очереди сборки.
2. **Цены:** синхронизировать актуальные цены, комиссии и ценовой карантин;
   записывающие методы держать за отдельным API-ключом.
3. **Финансы:** дополнить начисления транзакциями, отчетами реализации, услугами
   и сверкой документов.
4. **Возвраты и отмены:** хранить жизненный цикл возврата и причины отмены,
   добавить идемпотентную обработку статусов.
5. **FBO-поставки:** заявки, грузоместа, таймслоты и документы связать с уже
   сохраняемыми поставками.
6. **Продвижение:** расширить Performance API отчетами по товарам, поисковым
   фразам, расходам и заказам; операции изменения ставок изолировать от чтения.
7. **Уведомления:** использовать push-события для ускорения обновления заказов,
   сохранив периодическую сверку как защитный механизм.

Перед реализацией любого нового метода нужно повторно сверять его страницу в
официальной документации: Ozon независимо меняет версии и сроки отключения
операций.
