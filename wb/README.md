# Интеграция с Wildberries (`wb`)

Пакет `wb` — основной интеграционный слой проекта для чтения данных из API Wildberries и их сохранения в PostgreSQL. Он охватывает каталог, склады, API и сервисы остатков FBS/FBO, заказы, поставки FBW, финансовые отчёты, вопросы и отзывы, а также рекламу WB Продвижение. Периодический запуск остатков вынесен в отдельный пакет `inventory_sync`.

Документ описывает фактическое состояние каждого файла в папке `wb`.

## 1. Возможности пакета

Пакет умеет:

- загружать карточки товаров со всей вложенной структурой;
- сохранять предметы, характеристики, размеры, штрихкоды и фотографии;
- синхронизировать склады продавца и остатки FBS;
- сохранять текущий снимок остатков FBO на складах WB;
- загружать максимальную доступную историю заказов FBS и FBO;
- загружать склады, поставки, товары и упаковки FBW;
- сохранять финансовые отчёты продаж и эквайринга;
- получать вопросы и отзывы, хранить версии ответов и считать SLA;
- загружать кампании, бюджеты, расходы и статистику рекламы;
- рассчитывать ROAS, ДРР и CPO;
- запускать операции через единый фасад `WBSyncService`.

Большинство операций идемпотентны: повторный запуск обновляет существующие строки или игнорирует уже сохранённые операции.

## 2. Архитектура

Поток данных выглядит так:

```text
app/config.py
    ↓
WBClient
    ↓
API-модуль (ProductsAPI, PromotionAPI и другие)
    ↓
Service
    ↓
Repository или SQLAlchemy Session
    ↓
модели app/models.py → PostgreSQL
```

Уровни имеют следующие обязанности:

1. `WBClient` отвечает за HTTP, авторизацию, повторы и преобразование ошибок.
2. API-модули знают домен, endpoint, параметры и пагинацию WB.
3. Сервисы преобразуют ответы, связывают сущности и управляют транзакциями.
4. Репозитории инкапсулируют повторяющиеся запросы к БД.
5. `WBSyncService` предоставляет единую точку входа.

## 3. Конфигурация

Настройки читаются в `app/config.py` из `.env`.

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL PostgreSQL | обязательна |
| `WB_API_KEY` | основной токен WB | нет |
| `WB_PROMOTION_API_KEY` | отдельный токен категории «Продвижение» | `WB_API_KEY` |
| `WB_CONTENT_BASE_URL` | карточки и категории | `https://content-api.wildberries.ru` |
| `WB_MARKETPLACE_BASE_URL` | FBS, склады продавца и остатки | `https://marketplace-api.wildberries.ru` |
| `WB_ANALYTICS_BASE_URL` | аналитика и остатки FBO | `https://seller-analytics-api.wildberries.ru` |
| `WB_STATISTICS_BASE_URL` | исторические заказы и статистика | `https://statistics-api.wildberries.ru` |
| `WB_SUPPLIES_BASE_URL` | поставки FBW | `https://supplies-api.wildberries.ru` |
| `WB_FINANCE_BASE_URL` | финансовые отчёты | `https://finance-api.wildberries.ru` |
| `WB_FEEDBACKS_BASE_URL` | вопросы и отзывы | `https://feedbacks-api.wildberries.ru` |
| `WB_PROMOTION_BASE_URL` | реклама | `https://advert-api.wildberries.ru` |
| `WB_TIMEOUT_SECONDS` | таймаут одного HTTP-запроса | `30` |
| `WB_QUESTION_RESPONSE_SLA_HOURS` | SLA ответа на вопрос | `24` |
| `WB_FEEDBACK_RESPONSE_SLA_HOURS` | SLA ответа на отзыв | `24` |

Токены нельзя писать в исходный код, логи, тестовые фикстуры или документацию.

## 4. Инфраструктурные файлы

### `wb/__init__.py`

Обозначает `wb` как Python-пакет. Исполняемой логики и публичных импортов не содержит.

### `wb/base.py`

Содержит абстрактный класс `WBAPIBase`.

- принимает готовый `WBClient` или создаёт стандартный;
- хранит клиент в `self.client`;
- объявляет абстрактный метод `list(**kwargs)`.

Общий интерфейс `list()` позволяет единообразно использовать простые API-модули. Доменные методы вроде `balance()` или `statuses()` объявляются в конкретных классах.

### `wb/client.py`

Содержит базовый HTTP-клиент `WBClient`.

Конструктор:

```python
WBClient(api_key=None, base_url=None, timeout=None)
```

Поведение:

- создаёт `requests.Session`;
- передаёт токен без префикса в заголовке `Authorization`;
- добавляет `Content-Type: application/json` и `Accept: application/json`;
- объединяет `base_url` и относительный путь;
- поддерживает GET и POST;
- повторяет сетевые ошибки, ответы `429` и `5xx`;
- для `429` учитывает `Retry-After`, а без него ждёт 20 секунд; для сетевых ошибок и `5xx` использует задержку между повторами;
- возвращает `None` для `204 No Content` и пустого тела;
- преобразует успешный JSON в Python-структуру.

Публичные методы:

- `get(path, params=None, retries=3)`;
- `post(path, json_body=None, retries=3)`.

Клиент не реализует доменную пагинацию: она находится в соответствующих API-модулях.

### `wb/exceptions.py`

Иерархия исключений:

- `WBError` — базовая ошибка интеграции;
- `WBAuthError` — отсутствующий токен, HTTP 401 или 403;
- `WBRateLimitError` — лимит WB исчерпан после всех повторов;
- `WBHTTPError` — сеть, прочие HTTP-ошибки и исчерпанные повторы `5xx`;
- `WBParseError` — успешный ответ содержит невалидный JSON.

Потребитель может перехватывать `WBError` для всех ошибок WB или конкретный подкласс для отдельной реакции.

### `wb/endpoints.py`

Хранит константы путей для старых и базовых разделов API.

- `WBProductsEndpoints` — карточки товаров;
- `WBWarehousesEndpoints` — склады продавца;
- `WBStocksEndpoints` — остатки FBS;
- `WBFboStocksEndpoints` — остатки FBO;
- `WBOrdersEndpoints` — новые FBS-заказы, их статусы и исторические заказы;
- `WBCategoriesEndpoints` — предметы/категории;
- `WBEndpoints` — агрегирующий класс с короткими именами констант.

Часть новых модулей пока содержит пути непосредственно в коде. При дальнейшем развитии их можно последовательно перенести сюда.

## 5. API-модули

API-модули не сохраняют данные. Они валидируют аргументы, выполняют запросы и приводят ответ к `list[dict]` или `dict`.

### `wb/products.py` — `ProductsAPI`

Работает с Content API и получает карточки товаров.

`list(**kwargs)`:

- принимает настройки метода WB в `settings` либо отдельными именованными параметрами;
- поддерживает аргумент `limit`;
- использует cursor-пагинацию `updatedAt + nmID`;
- предотвращает бесконечный цикл при повторении курсора;
- возвращает плоский список карточек.

Пример:

```python
from wb.products import ProductsAPI

cards = ProductsAPI().list(limit=100)
```

### `wb/categories.py` — `CategoriesAPI`

Работает с Content API и получает список предметов/категорий.

`list(**kwargs)` передаёт параметры как query string и возвращает `payload["data"]` либо пустой список.

### `wb/warehouses.py` — `WarehousesAPI`

Получает склады продавца из Marketplace API.

`list(**kwargs)` выполняет GET и возвращает список складов. Параметры передаются напрямую в query string.

### `wb/stocks.py` — `StocksAPI`

Получает остатки FBS для одного склада продавца.

Обязательные аргументы `list()`:

- `warehouse_id` — ID склада WB;
- `chrt_ids` — список ID размеров WB.

Метод отправляет POST, извлекает `stocks` и добавляет `warehouseId` к каждой строке для последующего связывания.

### `wb/fbo_stocks.py` — `FBOStocksAPI`

Получает текущие остатки FBO из Seller Analytics.

Параметры `list()`:

- `limit`, по умолчанию 250000;
- `offset`, по умолчанию 0;
- `nm_ids` — необязательный фильтр товаров;
- `chrt_ids` — необязательный фильтр размеров.

Метод автоматически обходит offset-пагинацию до неполной страницы.

### `wb/orders.py`

Содержит два независимых клиента.

#### `FBSOrdersAPI`

Работает с Marketplace API.

- `list(date_from, date_to, limit=1000)` получает новые FBS-заказы и проходит пагинацию по полю `next`;
- даты преобразуются в Unix timestamp;
- между страницами выдерживается 0,21 секунды;
- `statuses(order_ids)` получает статусы пакетами до 1000 ID.

#### `OrdersHistoryAPI`

Работает со Statistics API.

- `list(date_from="2019-01-01")` получает доступную историю заказов;
- принимает `date` или строку;
- использует `flag=0`;
- выполняет запрос без повторов (`retries=1`).

### `wb/sales.py` — `SalesOperationsAPI`

Единый оперативный источник заказов, продаж и возвратов для всех схем исполнения.

- `orders(date_from)` читает `/api/v1/supplier/orders`;
- `sales(date_from)` читает `/api/v1/supplier/sales`;
- заказ идентифицируется по `srid`;
- продажа или возврат идентифицируется по `saleID`;
- общий limiter выдерживает 60 секунд между запросами Statistics API;
- при достижении условного лимита 80000 строк пагинация продолжается по `lastChangeDate`.

Этот API оперативный и предварительный. Окончательные денежные итоги сверяются с детализацией отчётов реализации.

### `wb/fbw_supplies.py` — `FBWSuppliesAPI`

Работает с Supplies API.

- `warehouses()` — склады поставок;
- `supplies(date_from, date_to, limit=1000)` — список поставок с offset-пагинацией;
- `list(**kwargs)` — псевдоним `supplies()`;
- `details(identifier, is_preorder=False)` — карточка поставки или предзаказа;
- `goods(identifier, is_preorder=False, limit=1000)` — товары поставки с пагинацией;
- `packages(supply_id)` — упаковки поставки.

Флаг `isPreorderID` определяет, является идентификатор ID поставки или ID предзаказа.

### `wb/finances.py` — `FinancesAPI`

Работает с Finance API.

- `balance()` — текущий баланс продавца;
- `sales_reports()` — реестр отчётов продаж;
- `sales_details()` — детализация продаж за период;
- `sales_details_by_report()` — детализация конкретного отчёта;
- `acquiring_reports()` — реестр отчётов эквайринга;
- `acquiring_details()` — детализация эквайринга за период;
- `acquiring_details_by_report()` — детализация конкретного отчёта.

Внутренние стратегии пагинации:

- `_offset_pages()` — `limit + offset`;
- `_rrd_pages()` — курсор `rrdId`, с защитой от неподвижного курсора.

`list(**kwargs)` по умолчанию вызывает `sales_reports()`.

### `wb/documents.py` — `DocumentsAPI`

Read-only модуль документов поддерживает получение категорий и списка документов,
фильтрацию по периоду и категории, offset-пагинацию, а также скачивание одного
документа или архива до 50 документов. `DocumentStorage` проверяет и атомарно
сохраняет декодированный файл в `WB_DOCUMENT_STORAGE_DIR`. Каждый формат хранится
отдельно в `wb_document_files`; повреждённые файлы выявляются по размеру и SHA-256.
Независимый `python -m wb.document_sync` обновляет метаданные, баланс и ограниченную
очередь файлов. Полная схема, права токена и production timer описаны в
[`DOCUMENTS.md`](DOCUMENTS.md).

### `wb/customer_communications.py` — `CustomerCommunicationsAPI`

Read-only клиент Feedbacks API. Он не отправляет и не редактирует ответы.

- `questions(is_answered, take=5000, **filters)`;
- `feedbacks(is_answered, take=5000, **filters)`;
- `question(question_id)`;
- `feedback(feedback_id)`;
- `unanswered_counts()`;
- `list(**kwargs)` возвращает вопросы, по умолчанию неотвеченные.

`take` должен находиться в диапазоне 1–10000. Списки запрашиваются с `skip=0` и сортировкой `dateDesc`; текущий код не обходит страницы после первой.

### `wb/promotion.py` — `PromotionAPI`

Read-only клиент WB Продвижение.

- `campaigns()` — список всех кампаний, разворачивает группировку по типу и статусу;
- `campaign_details(advert_ids)` — подробности максимум 50 кампаний через актуальный v2 endpoint;
- `balance()` — баланс, взаиморасчёт, бонусы и cashback;
- `campaign_budget(advert_id)` — бюджет одной кампании;
- `payments(date_from, date_to)` — история пополнений;
- `expenses(date_from, date_to)` — фактические рекламные расходы;
- `full_stats(advert_ids, date_from, date_to)` — статистика максимум 50 кампаний;
- `list()` — псевдоним `campaigns()`.

Для платежей, расходов и статистики период ограничен 31 календарным днём. Обратный диапазон запрещён.

`full_stats()` содержит потокобезопасный limiter: между запросами одного экземпляра `PromotionAPI` выдерживается 20 секунд. Это соответствует лимиту endpoint статистики. `clock` и `sleeper` внедряются через конструктор для тестирования.

## 6. Репозитории

### `wb/repositories/__init__.py`

Обозначает подпакет persistence-слоя. Публичные классы автоматически не реэкспортирует.

### `wb/repositories/base_repository.py` — `BaseRepository`

Универсальный типизированный репозиторий SQLAlchemy.

- `add(instance)` добавляет объект в текущую сессию;
- `get_first_by(**filters)` возвращает первую строку по `filter_by`.

Репозиторий не выполняет `commit`: транзакцией владеет сервис.

### `category_repository.py` — `CategoryRepository`

Работает с `WBSubject`. Метод `get_by_wb_id()` ищет предмет по ID WB.

### `product_repository.py` — `ProductRepository`

Работает с `WBProduct`. Метод `get_by_nm_id()` ищет карточку по артикулу WB.

### `warehouse_repository.py` — `WarehouseRepository`

Работает с `WBFBSWarehouse`. Метод `get_by_wb_id()` ищет склад продавца по ID WB.

### `stock_repository.py` — `StockRepository`

Работает с `WBFBSStock`. Метод `get_by_sku_and_warehouse()` ищет остаток по SKU и внутреннему ID склада.

### `promotion_repository.py` — `PromotionRepository`

Специализированный репозиторий рекламного домена.

Основные операции:

- загрузка кампаний в словарь по `advert_wb_id`;
- выбор ID кампаний с необязательной фильтрацией статусов;
- создание отсутствующей кампании с немедленным `flush()`;
- получение идентичностей ранее сохранённых расходов;
- сохранение расходов и пополнений;
- сопоставление `nm_id` с внутренними ID товаров;
- upsert дневной статистики кампании;
- получение товарных строк дня по ключу `(app_type, nm_id)`;
- удаление товарных строк, исчезнувших из свежего ответа;
- сохранение снимка баланса кабинета.

Все методы используют переданную сессию и не делают самостоятельный `commit`.

## 7. Сервисы

### `wb/services/__init__.py`

Экспортирует `WBSyncService` как основной публичный фасад сервисного слоя.

### `category_service.py` — `CategoryService`

`sync_from_api()` получает предметы и делает upsert `WBSubject` по `wb_id`. Обновляет название и сохраняет исходный JSON.

### `product_service.py` — `ProductService`

Загружает карточки и сохраняет их полную нормализованную структуру.

Наполняемые модели:

- `WBProduct`;
- `WBSubject`;
- `WBProductPhoto`;
- `WBProductDimensions`;
- `WBCharacteristic`;
- `WBProductCharacteristic`;
- `WBProductSize`;
- `WBSizeBarcode`.

Алгоритм:

1. Находит или создаёт товар по `nmID`.
2. Обновляет основные поля карточки и исходный JSON.
3. Находит или создаёт предмет.
4. Синхронизирует фотографии по позиции.
5. Обновляет единственную запись габаритов.
6. Синхронизирует справочник характеристик и значения товара.
7. Синхронизирует размеры и штрихкоды.
8. Удаляет дочерние элементы, которых больше нет в ответе WB.

`sync_from_api()` возвращает исходный список карточек после фиксации транзакции.

### `warehouse_service.py` — `WarehouseService`

Сохраняет склады продавца в `WBFBSWarehouse`. Upsert выполняется по `wb_id`; обновляются офис, тип груза, тип доставки, признаки удаления/обработки и raw JSON.

### `stock_service.py` — `StockService`

Сохраняет остатки FBS в `WBFBSStock`.

Для каждой строки должны уже существовать:

- `WBProductSize` с соответствующим `chrt_id`;
- `WBFBSWarehouse` с соответствующим ID WB.

Если зависимость не найдена, строка пропускается. Уникальная логическая запись определяется парой SKU + склад.

### `fbo_stock_service.py` — `FBOStockService`

Сохраняет текущий снимок FBO в:

- `WBFboWarehouse`;
- `WBFboStock`.

Склад определяется составным ключом `(warehouseId, warehouseName, regionName)`, остаток — `(size_id, warehouse_id)`.

Устаревший прямой вызов сервиса без фильтров `nm_ids/chrt_ids` считает ответ полным снимком:

- отсутствующие остатки удаляются;
- неиспользуемые склады FBO удаляются.

При частичной синхронизации данные вне фильтра не удаляются.

### `order_service.py`

#### `FBSOrderService`

`sync_max_history(start=None, end=None)`:

- по умолчанию проходит период с 2019 года до текущего времени;
- разбивает его на интервалы по 30 дней;
- сохраняет `WBFBSOrder` по `order_id`;
- связывает заказ с товаром, размером и складом, если они уже загружены;
- после загрузки запрашивает актуальные supplier/WB статусы пакетами.

Метод возвращает количество полученных строк, а не обязательно количество новых строк.

#### `FBOOrderService`

`sync_max_history()` получает историю из Statistics API, отделяет FBO от складов типа «продавец», делает upsert `WBFboOrder` по `srid` и связывает заказ с товаром и размером.

Возвращает `(все_полученные_заказы, сохраненные_FBO_заказы)`.

### `sales_service.py` — `SalesService`

Нормализует оперативные данные во всех схемах продаж:

- `WBOperationalOrder` — одна строка на заказ, уникальность по `srid`;
- `WBOperationalSale` — одна строка на продажу или возврат, уникальность по `saleID`.

`saleID`, начинающийся с `S`, считается выкупом; `R` — возвратом. Возврат хранится отдельной операцией и не перезаписывает исходный заказ.

`sync_all()` при первом запуске загружает доступные 90 дней, затем использует последнюю дату изменения с перекрытием.

`summary(date_from, date_to)` формирует согласованный отчёт:

- `orders_placed` — заказы, оформленные в периоде;
- `orders_from_period_now_cancelled` — сколько заказов этой когорты впоследствии отменено;
- `cancellations_registered` — отмены, зарегистрированные в периоде независимо от даты заказа;
- `buyouts` и `returns` — отдельные события по дате продажи/возврата;
- `net_buyouts = buyouts - returns`;
- чистая сумма равна сумме выкупов минус абсолютная сумма возвратов;
- FBS/FBO считаются отдельно по `warehouseType`;
- `operations_without_order_row` показывает продажи, для которых WB не вернул исходную строку `/orders`; они остаются в выкупах и не теряются;
- `accounting_report_through` показывает покрытие финансовой детализации;
- `accounting_covers_period` показывает, доступна ли бухгалтерская сверка периода.

Границы дня рассчитываются в `Europe/Moscow`.

### `fbw_supply_service.py` — `FBWSupplyService`

Загружает максимальную историю поставок FBW.

Наполняемые модели:

- `WBFbwWarehouse`;
- `WBFbwSupply`;
- `WBFbwSupplySnapshot`;
- `WBFbwSupplyGood`;
- `WBFbwSupplyPackage`;
- `WBFbwSupplyPackageGood`.

Сначала загружаются склады и список поставок. Детальные запросы выполняются только для изменившихся поставок. Между запросами выдерживается `REQUEST_INTERVAL = 6.1` секунды. Товары связываются с `WBProduct`, `WBProductSize` и `WBSizeBarcode`, если соответствующие записи существуют.

Результат `sync_max_history()` — словарь счётчиков складов, поставок, изменившихся поставок, товаров и упаковок.

### `finance_service.py` — `FinanceService`

Наполняет:

- `WBFinancialSalesReport`;
- `WBFinancialSalesRow`;
- `WBFinancialAcquiringReport`;
- `WBFinancialAcquiringRow`.

Методы:

- `sync_sales_reports()`;
- `sync_sales_details()`;
- `sync_acquiring_reports()`;
- `sync_acquiring_details()`.

Отчёты обновляются по `reportId`, детальные строки — по `rrdId`. Денежные значения преобразуются через `Decimal`; невалидное значение становится нулём. Строки продаж связываются с `WBProduct` по `nmId`. После детализации у затронутого отчёта обновляется `details_synced_at`.

Для эквайринга рассчитываются знаковые суммы: возврат получает `operation_sign = -1`, остальные операции — `1`.

### `customer_communication_service.py` — `CustomerCommunicationService`

Read-only сервис вопросов и отзывов. Он ничего не отправляет покупателям.

Наполняет:

- `WBCustomerQuestion` и версии `WBCustomerQuestionAnswer`;
- `WBCustomerFeedback` и версии `WBCustomerFeedbackAnswer`.

`sync_all()` отдельно получает отвеченные и неотвеченные вопросы/отзывы. Основные строки обновляются по внешнему ID; новая версия ответа добавляется по комбинации родительской записи, времени ответа и текста.

Дополнительно рассчитываются:

- время ответа в секундах;
- нарушение SLA;
- простая эвристическая оценка качества ответа 0–100;
- возможность/необходимость ответа на отзыв.

`quality_summary()` возвращает для вопросов и отзывов количество записей, отвеченные, просроченные, нарушения SLA, среднее время ответа и среднюю оценку качества.

### `promotion_service.py` — `PromotionService`

Главный сервис рекламного кабинета.

Конструктор позволяет внедрить `PromotionAPI`, фабрику сессий и дополнительную задержку между запросами. Это упрощает тестирование.

Методы синхронизации:

- `sync_campaigns()` — базовые ID, типы и статусы кампаний;
- `sync_campaign_details()` — подробные настройки пакетами до 50 ID;
- `sync_account_balance()` — новый снимок баланса кабинета;
- `sync_campaign_budgets()` — бюджет выбранных кампаний с интервалом 0,25 секунды;
- `sync_payments()` — идемпотентная история пополнений;
- `sync_expenses()` — идемпотентная история расходов;
- `sync_stats()` — дневная и товарная статистика кампаний;
- `sync_all()` — полный сценарий за произвольный период.

`sync_all()`:

1. Обновляет список кампаний.
2. Загружает подробности.
3. Создаёт снимок баланса.
4. Загружает бюджеты только для статусов 4, 9 и 11.
5. Разбивает период на интервалы по 31 календарному дню.
6. Для каждого интервала загружает пополнения и расходы.
7. Делит кампании на пакеты по 50 и загружает статистику.

Результат содержит счётчики:

```python
{
    "campaigns_received": 0,
    "campaign_details_received": 0,
    "campaign_budgets_updated": 0,
    "payments_inserted": 0,
    "expenses_inserted": 0,
    "daily_stats_upserted": 0,
}
```

Расходы идентифицируются составом `updNum + advertId + время + сумма + тип оплаты`. Один `updNum` использовать нельзя: в реальных данных он не является глобально уникальным.

Статистика сохраняется в:

- `WBAdvertCampaign`;
- `WBAdvertExpense`;
- `WBAdvertDailyStat`;
- `WBAdvertProductDailyStat`;
- `WBPromotionAccountSnapshot`;
- `WBPromotionPayment`.

`efficiency_summary(date_from=None, date_to=None, advert_ids=None)` агрегирует данные на стороне SQL и возвращает расход, атрибутированную выручку, заказы, ROAS, ДРР и CPO.

Формулы:

```text
ROAS = attributed_revenue / spend
ДРР (%) = spend / attributed_revenue × 100
CPO = spend / orders
```

### `sync_service.py` — `WBSyncService`

Фасад всего пакета. При создании инициализирует все сервисы и публикует ссылки на основные API-клиенты для обратной совместимости.

Методы:

| Метод | Делегирует |
|---|---|
| `sync_products()` | `ProductService.sync_from_api()` |
| `sync_categories()` | `CategoryService.sync_from_api()` |
| `sync_warehouses()` / `sync_fbs_warehouses()` | `WarehouseService.sync_from_api()` |
| `sync_stocks()` / `sync_fbs_stocks()` | `StockService.sync_from_api()` |
| `sync_fbo_stocks()` | `FBOStockService.sync_from_api()` |
| `sync_fbs_orders_max_history()` | `FBSOrderService.sync_max_history()` |
| `sync_fbo_orders_max_history()` | `FBOOrderService.sync_max_history()` |
| `sync_fbw_supplies_max_history()` | `FBWSupplyService.sync_max_history()` |
| `sync_financial_sales_reports()` | `FinanceService.sync_sales_reports()` |
| `sync_financial_sales_details()` | `FinanceService.sync_sales_details()` |
| `sync_financial_acquiring_reports()` | `FinanceService.sync_acquiring_reports()` |
| `sync_financial_acquiring_details()` | `FinanceService.sync_acquiring_details()` |
| `sync_customer_communications()` | `CustomerCommunicationService.sync_all()` |
| `customer_communication_quality()` | расчёт качества общения |
| `sync_advert_campaigns()` | список рекламных кампаний |
| `sync_advert_expenses()` | расходы рекламы |
| `sync_advert_stats()` | статистика рекламы |
| `sync_advertising()` | полная синхронизация рекламы |
| `advert_efficiency()` | рекламные показатели |

### `wb/scheduler.py` — `WBPeriodicSync`

Последовательно запускает общий цикл WB без остатков и повторяет его через настроенный интервал. Остатки запускаются отдельным worker `python -m inventory_sync --marketplace wb`. Одновременно может выполняться только один общий WB-цикл.

Порядок задач:

1. категории;
2. карточки и размеры;
3. склады FBS;
4. заказы FBS;
5. единый поток оперативных заказов, выкупов и возвратов;
6. поставки FBW;
7. финансовые отчёты и их детализация;
8. вопросы и отзывы;
9. реклама.

`SyncSettings` читает общий интервал, историческую начальную дату, рекламное окно и перекрытие заказов из `app/config.py`. Первый FBS-запуск начинается с `WB_SYNC_HISTORY_START`; последующие — с даты последнего заказа минус перекрытие.

`run_cycle()` возвращает результат каждой задачи, её статус и длительность. Ошибка одного независимого раздела логируется и не отменяет оставшиеся разделы; это позволяет обновить доступные данные при временном сбое отдельного API WB.

`run_forever()` ждёт завершения цикла и только затем отсчитывает новый интервал, поэтому циклы не накладываются друг на друга. `stop()` и обработчики `SIGINT/SIGTERM` обеспечивают штатное завершение.

### `wb/sync_logging.py` — журналирование синхронизации

Универсальный модуль диагностики WB. Он создаёт:

- `logs/wb/wb_sync.log` — ход циклов и задач;
- `logs/wb/wb_errors.jsonl` — структурированные ошибки;
- записи `WBSyncRun` и `WBSyncError` в PostgreSQL.

Ошибка содержит ID цикла, задачу, этап (`task`, `exchange`, `exchange_parse` или `logging_database`), тип и текст исключения, файл, модуль, функцию, номер и текст строки, полный traceback и безопасный контекст. Токены, пароли и Authorization маскируются; большие значения обрезаются.

Логи ротируются по размеру. Если запись ошибки в PostgreSQL сама завершилась неудачно, исходная ошибка и ошибка журналирования остаются в JSONL-файле.

Последние ошибочные циклы можно посмотреть SQL-запросом:

```sql
SELECT id, status, started_at, finished_at, tasks_failed
FROM wb_sync_runs
WHERE tasks_failed > 0
ORDER BY started_at DESC;
```

Детали ошибок:

```sql
SELECT cycle_id, task, phase, exception_type, message,
       file, line, function, created_at
FROM wb_sync_errors
ORDER BY created_at DESC;
```

## 8. Рекомендуемый порядок первой загрузки

Связи с товарами, размерами и складами заполняются только при наличии справочных записей. Для пустой БД рекомендуется:

```python
from wb.services import WBSyncService

sync = WBSyncService()

sync.sync_categories()
sync.sync_products(limit=100)
sync.sync_fbs_warehouses()

# Для каждого склада передать его WB ID и список chrtID.
sync.sync_fbs_stocks(warehouse_id=123, chrt_ids=[111, 222])

sync.sync_fbo_stocks()
sync.sync_fbs_orders_max_history()
sync.sync_fbo_orders_max_history()
sync.sync_fbw_supplies_max_history()
sync.sync_financial_sales_reports()
sync.sync_financial_sales_details()
sync.sync_financial_acquiring_reports()
sync.sync_financial_acquiring_details()
sync.sync_customer_communications()
```

Реклама за период:

```python
from datetime import date
from wb.services import WBSyncService

result = WBSyncService().sync_advertising(
    date_from=date(2026, 7, 1),
    date_to=date(2026, 7, 31),
)
print(result)
```

Аналитика рекламы:

```python
summary = WBSyncService().advert_efficiency(
    date_from=date(2026, 7, 1),
    date_to=date(2026, 7, 31),
    advert_ids=[123456],
)
```

## 9. Периодический запуск

Настройки `.env`:

```dotenv
WB_SYNC_INTERVAL_SECONDS=21600
WB_SYNC_RUN_ON_START=true
WB_SYNC_HISTORY_START=2019-01-01
WB_SYNC_PROMOTION_LOOKBACK_DAYS=31
WB_SYNC_FBS_ORDER_OVERLAP_DAYS=2
WB_SYNC_FINANCE_OVERLAP_DAYS=7
WB_ORDER_FEED_LOOKBACK_DAYS=31
WB_ORDER_FEED_MAX_AGE_SECONDS=1200
WB_LOG_DIR=logs/wb
WB_LOG_LEVEL=INFO
WB_LOG_MAX_BYTES=10485760
WB_LOG_BACKUP_COUNT=10
```

WB worker не запускает Telegram и остатки. Запустить один полный цикл для проверки:

```powershell
.\.venv\Scripts\python.exe -m wb --once
```

Запустить постоянный процесс:

```powershell
.\.venv\Scripts\python.exe -m wb
```

Интервал отсчитывается после завершения предыдущего полного цикла. Для остановки нажмите `Ctrl+C`.
В production процесс работает как `wbozon-wb.service`. Корневой `main.py` оставлен только как совместимый alias этой же точки запуска.

Полная realtime-лента заказов работает независимо от общего цикла:

```powershell
.\.venv\Scripts\python.exe -m wb.order_feed_sync
```

В production её запускает `wbozon-wb-order-feed.timer` каждые 10 минут. Данные
сохраняются по уникальному `srid` в `wb_order_feed_orders`, а результаты запусков
— в `wb_order_feed_sync_runs`. Именно эта таблица используется для количества и
суммы заказов в групповом Telegram-отчёте.

## 10. Транзакции и идемпотентность

- API-модули не открывают сессии БД.
- Сервис обычно открывает одну транзакцию на полученную порцию данных.
- Репозитории не делают `commit`.
- При исключении до `commit` контекст SQLAlchemy закрывает сессию без фиксации незавершённых изменений.
- Основные сущности обновляются по внешнему уникальному ключу WB.
- Вложенные коллекции каталога и рекламы синхронизируются с актуальным ответом.
- `raw_data` сохраняется для диагностики изменений контракта WB.

Не все возвращаемые счётчики означают новые строки. Например, сервисы заказов и карточек чаще возвращают число полученных объектов. Методы рекламных расходов и пополнений возвращают число фактически вставленных записей.

## 11. Ограничения и эксплуатационные замечания

- Токен должен содержать категории доступа для используемых разделов WB.
- Лимиты запросов различаются по endpoint; нельзя задавать одну общую частоту для всего API.
- Полная рекламная статистика намеренно работает медленно из-за интервала 20 секунд.
- `CustomerCommunicationsAPI` сейчас читает только первую страницу до 10000 записей.
- Исторический FBS sync с 2019 года может выполняться долго.
- `FBWSupplyService` детально обходит только изменившиеся поставки, но каждый объект требует нескольких запросов.
- Периодическая загрузка остатков вынесена в `inventory_sync`: исчезнувшие позиции FBS/FBO обнуляются, а в 00:00 по Москве создаётся отдельный исторический срез.
- Некоторые связи остаются `NULL`, если каталог был загружен после заказов, финансов или рекламы. После первой загрузки следует повторить зависимые синхронизации.
- Метрики рекламы являются атрибутированными данными WB, а не полной бухгалтерской прибылью.
- В коде ещё встречаются `datetime.utcnow()`, которые Python 3.13 помечает устаревающими; будущий рефакторинг должен перейти на timezone-aware UTC.

## 12. Тестирование

Основные тесты находятся в:

- `tests/test_wb_client.py` — транспорт, повторы, ошибки и `204 No Content`;
- `tests/test_wb_api_modules.py` — контракты endpoint и пагинация;
- `tests/test_wb_services.py` — фасад и делегирование;
- `tests/test_wb_product_mapping.py` — идемпотентное сохранение каталога;
- `tests/test_promotion_service.py` — периоды и идентичность рекламных операций.
- `tests/test_wb_scheduler.py` — порядок задач, изоляция ошибок и запрет пересечения циклов.
- `tests/test_wb_sync_logging.py` — traceback, координаты ошибки и маскирование секретов.

Запуск:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Проверка миграций:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
```

Следует использовать `python -m alembic`, поскольку прямой запуск `alembic.exe` в этой среде может не добавить корень проекта в `sys.path`.

## 13. Как добавлять новый раздел WB API

1. Добавить base URL в `app/config.py`, если используется новый домен.
2. Создать API-модуль в `wb/` и унаследовать класс от `WBAPIBase`.
3. Реализовать в API-модуле валидацию, endpoint и пагинацию.
4. Добавить SQLAlchemy-модели и Alembic-миграцию, если данные сохраняются.
5. Добавить repository для повторяющихся запросов к БД.
6. Реализовать сервис с явной границей транзакции.
7. Подключить сервис к `WBSyncService`.
8. Добавить тесты транспорта/API отдельно от тестов persistence-логики.
9. Проверить повторный запуск на отсутствие дублей.
10. Обновить этот README.
