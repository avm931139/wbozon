#matra_sync/core/db/models

from sqlalchemy import (Column, Integer, String, ForeignKey, Float, Boolean, Text, JSON, Column, String,
                        DateTime, BIGINT, TIMESTAMP, Numeric, BigInteger, UniqueConstraint, Index)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.declarative import declarative_base
from core.db.connection import engine
from datetime import datetime
from typing import Optional, Dict, Any, List


Base = declarative_base()


class Ul(Base):
    __tablename__ = "ul"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True,
                                    comment="Внутренний ID организации")

    name: Mapped[str] = mapped_column(Text, nullable=False,
                                      comment="Название организации")

    inn: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                               comment="ИНН организации")

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения")

    # Связи
    wb_cards: Mapped[List["WbCard"]] = relationship(back_populates="ul")
    wb_stock_seller: Mapped[List["WbStockSeller"]] = relationship(back_populates="ul")
    wb_stock: Mapped[List["WbStock"]] = relationship(back_populates="ul")
    wb_remains_reports: Mapped[List["WbRemainsReport"]] = relationship(back_populates="ul")

    ozon_cards: Mapped[List["OzonCard"]] = relationship(back_populates="ul")
    ozon_stocks: Mapped[List["OzonStockSeller"]] = relationship(back_populates="ul")

# --------------WB

class WbCard(Base):
    __tablename__ = "wb_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True,
                                    comment="Внутренний ID записи")

    nm_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True,
                                       comment="Артикул WB")
    imt_id: Mapped[int] = mapped_column(BIGINT, nullable=False,
                                        comment="ID объединённой карточки товара")
    nm_uuid: Mapped[str] = mapped_column(String, nullable=False,
                                         comment="UUID карточки товара")

    subject_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                            comment="ID предмета (категории)")
    subject_name: Mapped[str] = mapped_column(String, nullable=False,
                                              comment="Название предмета (категории)")

    vendor_code: Mapped[str] = mapped_column(String, nullable=False,
                                             comment="Артикул продавца")
    brand: Mapped[Optional[str]] = mapped_column(String, nullable=True,
                                                 comment="Бренд товара")
    title: Mapped[str] = mapped_column(String, nullable=False,
                                       comment="Наименование товара")
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True,
                                                       comment="Описание товара")

    need_kiz: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                           comment="Требуется код маркировки")

    photos: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                             comment="Фото товара")
    video: Mapped[Optional[str]] = mapped_column(String, nullable=True,
                                                 comment="URL видео")
    wholesale: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                                comment="Оптовая продажа")
    dimensions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                                 comment="Габариты и вес")
    characteristics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                                      comment="Характеристики")
    sizes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                            comment="Размеры")
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                           comment="Ярлыки")

    skus: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                                comment="Баркод ВБ")

    # Внешний ключ на организацию
    id_ul: Mapped[int] = mapped_column(ForeignKey("ul.id", ondelete="CASCADE"),
                                       nullable=False, comment="ИД организации")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 comment="Дата создания")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата изменения")

    # Связь с организацией
    ul: Mapped["Ul"] = relationship(back_populates="wb_cards")

#-------------------Для загрузки товаров
class WBSubject(Base):
    """Категории Wildberries"""
    __tablename__ = "wb_subject"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    subject_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, comment="ID категории в Wildberries")
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название категории")
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="ID родительской категории")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связь с характеристиками (один ко многим)
    characteristics: Mapped[List["WBCharacteristic"]] = relationship(
        "WBCharacteristic",
        back_populates="subject",
        cascade="all, delete-orphan"
    )

    # Связь с промежуточной таблицей (один ко многим)
    subject_characteristics: Mapped[List["WBSubjectCharacteristic"]] = relationship(
        "WBSubjectCharacteristic",
        back_populates="subject",
        cascade="all, delete-orphan"
    )


class WBCharacteristic(Base):
    """Характеристики категорий Wildberries"""
    __tablename__ = "wb_characteristic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Внешний ключ
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wb_subject.subject_id", ondelete="CASCADE"),
        nullable=False,
        comment="ID категории в Wildberries"
    )

    char_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="ID характеристики")
    char_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Название характеристики")
    char_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="Тип характеристики")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, comment="Обязательная")
    is_collection: Mapped[bool] = mapped_column(Boolean, default=False, comment="Множественный выбор")
    is_multiple: Mapped[bool] = mapped_column(Boolean, default=False, comment="Множественное значение")
    max_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Максимальная длина")
    unit_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Единица измерения")
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False, comment="Популярная")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Описание")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связь с категорией (многие к одному)
    subject: Mapped["WBSubject"] = relationship(
        "WBSubject",
        back_populates="characteristics",
        foreign_keys=[subject_id]
    )

    # Связь с промежуточной таблицей (один ко многим)
    subject_links: Mapped[List["WBSubjectCharacteristic"]] = relationship(
        "WBSubjectCharacteristic",
        back_populates="characteristic",
        cascade="all, delete-orphan"
    )


# -----------------Склады остатки

class WbWarehouseSellers(Base):
    __tablename__= 'wb_wharehouse_seller'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_wb_warehouse: Mapped[int] = mapped_column(Integer, comment='ID склада продавца')
    name: Mapped[str] = mapped_column(Text, comment='Название склада продавца')
    office_id: Mapped[int] = mapped_column(Integer, comment='ID склада WB')
    cargoType: Mapped[int] = mapped_column(Integer, comment='Тип товара:1 — малогабаритный товар МГТ '
                                                            '2 — сверхгабаритный товар '
                                                            'СГТ3 — крупногабаритный товар КГТ+')
    deliveryType: Mapped[bool] = mapped_column(Boolean, comment='Тип доставки, который принимает склад:'
                                                                '1 — доставка на склад WB FBS'
                                                                '2 — доставка силами продавца (DBS)'
                                                                '3 — доставка курьером WB (DBW)'
                                                                '5 — самовывоз (C&C)'
                                                                '6 — экспресс-доставка силами продавца (ЕDBS)')
    is_deleting: Mapped[bool] = mapped_column(Boolean, comment='Склад удаляется:')
    is_processing: Mapped[bool] = mapped_column(Boolean, comment='Данные склада обновляются:')
    is_processing: Mapped[bool] = mapped_column(Boolean, comment='Данные склада обновляются:')

    created_at = Column(DateTime, nullable=False, comment="Дата и время создания")
    updated_at = Column(DateTime, comment="Дата и время изменения")


class WbStockSeller(Base):
    __tablename__ = "wb_stock_seller"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("mantra_products.id", ondelete="CASCADE"))
    type_wharehouse: Mapped[str] = mapped_column(Text, nullable=False, comment='Тип склада fbs fbo')
    artikul_wb: Mapped[str] = mapped_column(Text, nullable=False, comment='артикул ВБ')
    nm_id_wb: Mapped[int] = mapped_column(ForeignKey("wb_cards.nm_id", ondelete="CASCADE"))
    pcs: Mapped[int] = mapped_column(Integer, comment='Остатки товара у поставщика')
    wharehouse_seller_wb: Mapped[int] = mapped_column(Integer, nullable=False, comment='ID склада продавца на ВБ')

    id_ul: Mapped[int] = mapped_column(ForeignKey("ul.id", ondelete="CASCADE"),
                                       nullable=False, comment="ИД организации")

    # Связи
    ul: Mapped["Ul"] = relationship(back_populates="wb_stock_seller")

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения остатка")


class WbStock(Base):
    __tablename__ = "wb_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Text, nullable=False, comment='product_id')
    type_wharehouse: Mapped[str] = mapped_column(Text, nullable=False, comment='Тип склада fbs fbo')
    artikul_wb: Mapped[str] = mapped_column(Text, nullable=False, comment='артикул ВБ')
    nm_id_wb: Mapped[int] = mapped_column(ForeignKey("wb_cards.nm_id", ondelete="CASCADE"))
    pcs: Mapped[int] = mapped_column(Integer, comment='Остатки товара у поставщика')
    wharehouse_seller_wb: Mapped[int] = mapped_column(Integer, nullable=False, comment='ID склада продавца на ВБ')

    id_ul: Mapped[int] = mapped_column(ForeignKey("ul.id", ondelete="CASCADE"),
                                       nullable=False, comment="ИД организации")

    # Связи
    ul: Mapped["Ul"] = relationship(back_populates="wb_stock")

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения остатка")


class WBStockLog(Base):
    __tablename__ = "wb_stock_log"
    __table_args__ = {"comment": "Логи отправки остатков товаров на Wildberries"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="Внутренний ID записи лога")
    sku: Mapped[str] = mapped_column(Text, nullable=False, comment="Баркод товара")
    amount: Mapped[int] = mapped_column(Integer, nullable=False, comment="Количество для отправки")
    status: Mapped[str] = mapped_column(String(50), nullable=False, comment="Статус отправки: success/fail")
    error: Mapped[str] = mapped_column(Text, nullable=True, comment="Описание ошибки, если отправка неуспешна")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, comment="Время логирования записи")


class WbRemainsReport(Base):
    __tablename__ = "wb_remains_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="ID задачи в WB")
    params: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True, comment="Параметры отчета")
    status: Mapped[str] = mapped_column(String(50), nullable=False, comment="Статус отчета")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="Прогресс выполнения")
    total: Mapped[int] = mapped_column(Integer, default=0, comment="Всего записей")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Ошибка если есть")
    records_count: Mapped[int] = mapped_column(Integer, default=0, comment="Количество записей в отчете")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="Время создания задачи")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="Время обновления статуса")
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                              comment="Время скачивания отчета")
    id_ul: Mapped[int] = mapped_column(ForeignKey("ul.id", ondelete="CASCADE"), nullable=False,
                                       comment="ИД организации")

    # Связи
    ul: Mapped["Ul"] = relationship(back_populates="wb_remains_reports")
    data: Mapped[List["WbRemainsReportData"]] = relationship(back_populates="report", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_wb_remains_task_id', 'task_id'),
        Index('idx_wb_remains_status', 'status'),
        Index('idx_wb_remains_created', 'created_at'),
    )


class WbRemainsReportData(Base):
    __tablename__ = "wb_remains_report_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("wb_remains_reports.id", ondelete="CASCADE"), nullable=False)

    # Данные из отчета
    nm_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="Артикул WB")
    vendor_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Артикул продавца")
    barcode: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Штрихкод")
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Бренд")
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Предмет")

    # Количество
    quantity: Mapped[int] = mapped_column(Integer, default=0, comment="Доступное количество")
    quantity_full: Mapped[int] = mapped_column(Integer, default=0, comment="Полное количество")
    quantity_not_in_orders: Mapped[int] = mapped_column(Integer, default=0, comment="Не в заказах")
    in_way_to_client: Mapped[int] = mapped_column(Integer, default=0, comment="В пути к клиенту")
    in_way_from_client: Mapped[int] = mapped_column(Integer, default=0, comment="В пути от клиента")

    # Цена
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, comment="Цена")

    # Склад
    warehouse_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="ID склада")
    warehouse_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="Название склада")

    # Оригинальные данные
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True, comment="Оригинальные данные")

    # Связи
    report: Mapped["WbRemainsReport"] = relationship(back_populates="data")

    __table_args__ = (
        Index('idx_wb_remains_data_report', 'report_id'),
        Index('idx_wb_remains_data_nm', 'nm_id'),
        Index('idx_wb_remains_data_barcode', 'barcode'),
    )

# -------------------Заказы ФБС ВБ
class WbFbsOrder(Base):
    __tablename__ = "wb_fbs_orders"

    # ===== Основные идентификаторы =====
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        comment="ID сборочного задания (уникальный идентификатор в системе WB)"
    )

    order_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="UID заказа покупателя (одинаковый для всех заданий одной корзины)"
    )

    rid: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="ID заказа в системе Wildberries"
    )

    # ===== Информация о товаре =====
    article: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Артикул товара (артикул продавца)"
    )

    nm_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Номенклатура WB (ID товара в каталоге Wildberries)"
    )

    chrt_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID товара в рамках конкретного заказа"
    )

    skus: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Массив SKU товара (штрих-коды) в формате JSON"
    )

    # ===== Ценовая информация =====
    price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Цена за единицу товара в валюте продавца"
    )

    final_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Финальная цена с учетом всех скидок"
    )

    sale_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Цена со скидкой (передается от Wildberries)"
    )

    converted_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Конвертированная цена в валюту, указанную в convertedCurrencyCode"
    )

    converted_final_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Конвертированная финальная цена"
    )

    # ===== Валютная информация =====
    currency_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Код валюты цены (например, 643 - RUB, 933 - BYN)"
    )

    converted_currency_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Код валюты конвертированной цены"
    )

    # ===== Информация о доставке =====
    delivery_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Тип доставки (fbs, fby и т.д.)"
    )

    cargo_type: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Габаритный тип товара (1 - маленький, 2 - большой и т.д.)"
    )

    cross_border_type: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Тип кроссбордерной доставки (0 - обычный, 1 - кроссбордер)"
    )

    # ===== Информация о складе и офисе =====
    warehouse_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID склада"
    )

    office_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID пункта выдачи заказов (ПВЗ) или склада"
    )

    offices: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Список доступных офисов/ПВЗ для доставки (JSON массив)"
    )

    # ===== Метаданные маркировки =====
    required_meta: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Обязательные метаданные для маркировки (например, ['uin', 'sgtin'])"
    )

    optional_meta: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Опциональные метаданные для маркировки"
    )

    # ===== Дополнительная информация =====
    address: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Адрес доставки (полный адрес, координаты) в формате JSON"
    )

    comment: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="Комментарий к заказу от покупателя"
    )

    scan_price: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Цена при сканировании (используется для некоторых типов заказов)"
    )

    color_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Код цвета товара (например, RAL 3017)"
    )

    is_zero_order: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        default=False,
        comment="Флаг нулевого заказа (True - заказ с нулевой стоимостью)"
    )

    options: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Дополнительные опции заказа (например, B2B флаг) в формате JSON"
    )

    user_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="ID пользователя (если доступен)"
    )

    # ===== Системные поля =====
    created_at_wb: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Дата и время создания заказа в системе Wildberries (из поля createdAt)"
    )

    loaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Дата и время загрузки записи в нашу БД"
    )

    # ===== Поле для отправки в Telegram =====
    send_mes_tg: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг отправки заказа в Telegram. False - не отправлено, True - отправлено"
    )

    sent_to_tg_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Дата и время отправки уведомления в Telegram"
    )

    # ===== Индексы для оптимизации запросов =====
    __table_args__ = (
        Index('idx_order_uid', 'order_uid'),  # для поиска по UID заказа
        Index('idx_created_at_wb', 'created_at_wb'),  # для сортировки по дате
        Index('idx_send_mes_tg', 'send_mes_tg'),  # для выборки неотправленных заказов
        Index('idx_loaded_at', 'loaded_at'),  # для выборки по времени загрузки
        Index('idx_nm_id', 'nm_id'),  # для поиска по номенклатуре
        Index('idx_warehouse_id', 'warehouse_id'),  # для поиска по складу
    )

    def __repr__(self) -> str:
        return f"<WbFbsOrder(id={self.id}, order_uid={self.order_uid}, article={self.article})>"

# --------------Озон

class OzonCard(Base):
    __tablename__ = "ozon_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Основные идентификаторы
    product_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, comment="ID товара в Ozon")
    offer_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="Артикул продавца")
    sku: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="SKU товара")

    # Наименование и описание
    name: Mapped[str] = mapped_column(Text, nullable=False, comment="Название товара")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Описание товара")

    # Категории
    description_category_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True,
                                                                   comment="ID категории описания")
    type_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="ID типа товара")

    # Цены и валюта
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, comment="Текущая цена")
    old_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, comment="Старая цена")
    min_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, comment="Минимальная цена")
    currency_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="Код валюты")
    vat: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="Ставка НДС")

    # Штрихкоды
    barcodes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Штрихкоды через ;")

    # Изображения
    images: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="URL изображений через ;")
    primary_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Главное изображение")
    images360: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="3D изображения через ;")
    color_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Цветное изображение")

    # Характеристики
    volume_weight: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True, comment="Объемный вес")
    is_kgt: Mapped[bool] = mapped_column(Boolean, default=False, comment="Крупногабаритный товар")
    is_prepayment_allowed: Mapped[bool] = mapped_column(Boolean, default=False, comment="Разрешена предоплата")

    # Статусы
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, comment="В архиве")
    is_autoarchived: Mapped[bool] = mapped_column(Boolean, default=False, comment="Автоматически в архиве")
    is_discounted: Mapped[bool] = mapped_column(Boolean, default=False, comment="Есть скидка")
    has_discounted_fbo_item: Mapped[bool] = mapped_column(Boolean, default=False, comment="Есть товар со скидкой FBO")
    discounted_fbo_stocks: Mapped[int] = mapped_column(Integer, default=0, comment="Остатки со скидкой FBO")
    visible: Mapped[bool] = mapped_column(Boolean, default=True, comment="Видимый")

    # Статусы модерации (JSON поля)
    statuses: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Статусы товара")
    visibility_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True,
                                                                         comment="Детали видимости")
    price_indexes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Индексы цен")

    # Остатки (JSON)
    stocks: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Информация об остатках")
    availabilities: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Доступность")

    # Комиссии (JSON)
    commissions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Комиссии")

    # Промо и источники
    promotions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Промоакции")
    sources: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Источники")
    model_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Информация о модели")

    # Ошибки
    errors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, comment="Ошибки")

    # Даты
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="Дата создания в Ozon")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="Дата обновления в Ozon")
    last_api_update: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now,
                                                      comment="Последнее обновление из API")

    # Привязка к организации
    id_ul: Mapped[int] = mapped_column(ForeignKey("ul.id", ondelete="CASCADE"), nullable=False,
                                       comment="ИД организации")

    # Связи
    ul: Mapped["Ul"] = relationship(back_populates="ozon_cards")

    __table_args__ = (
        Index('idx_ozon_cards_product_id', 'product_id'),
        Index('idx_ozon_cards_offer_id', 'offer_id'),
        Index('idx_ozon_cards_sku', 'sku'),
        Index('idx_ozon_cards_created_at', 'created_at'),
        Index('idx_ozon_cards_id_ul', 'id_ul'),
    )


class OzonStockSeller(Base):
    __tablename__ = "ozon_stock_seller"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="ID товара в Ozon")
    offer_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="Артикул")
    sku: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="SKU товара")
    present: Mapped[int] = mapped_column(Integer, default=0, comment="Доступное количество")
    reserved: Mapped[int] = mapped_column(Integer, default=0, comment="Зарезервированное количество")
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="Источник (fbs/fbo)")

    id_ul: Mapped[int] = mapped_column(ForeignKey("ul.id", ondelete="CASCADE"), nullable=False,
                                       comment="ИД организации")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now,
                                                 comment="Время обновления")

    # Связи
    ul: Mapped["Ul"] = relationship(back_populates="ozon_stocks")

    __table_args__ = (
        Index('idx_ozon_stock_product_id', 'product_id'),
        Index('idx_ozon_stock_sku', 'sku'),
        Index('idx_ozon_stock_id_ul', 'id_ul'),
    )

# --------------Мой склад

class MsShops(Base):
    __tablename__ = 'ms_shops_rel'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name: Mapped[Optional[str]] = mapped_column(String(255), comment='Наименование магазина')
    wh_id_ms: Mapped[Optional[str]] = mapped_column(String(255), comment="ID мойсклада склада")
    project_id_ms: Mapped[Optional[str]] = mapped_column(String(255), comment="ID мойсклада проекта")
    organization_id_ms: Mapped[Optional[str]] = mapped_column(String(255), comment="ID мойсклада Организации")
    comments: Mapped[Optional[str]] = mapped_column(String(255), comment="Комментарий")


class MSProduct(Base):
    __tablename__ = 'ms_product'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuidHref: Mapped[Optional[str]] = mapped_column(String(255), comment='ссылка на товар')
    id_ms: Mapped[Optional[str]] = mapped_column(String(255), index=True, comment='ID товара')
    type: Mapped[Optional[str]] = mapped_column(String(255), comment='Тип товара')
    name: Mapped[Optional[str]] = mapped_column(String(255), index=True, comment='Название товара')
    code: Mapped[Optional[str]] = mapped_column(String(255), comment='Код товара')
    article: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='Артикул товара')
    externalCode: Mapped[Optional[str]] = mapped_column(String(255), comment='Внешний код товара')
    pathName: Mapped[Optional[str]] = mapped_column(Text, comment='Группа товара')
    product_folder_id: Mapped[Optional[str]] = mapped_column(String(255), comment='ID группы товара')
    product_folder_name: Mapped[Optional[str]] = mapped_column(String(255), comment='Название группы товара')
    barcodes: Mapped[Optional[str]] = mapped_column(Text, comment='ШК товара')
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, comment='Доп поля товара')
    deleted: Mapped[Optional[bool]] = mapped_column(Boolean, comment='Товар удален')


class MSStock(Base):
    __tablename__ = "ms_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    moment: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment='Дата на начало дня остатка товара')
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    warehouse_id: Mapped[Optional[str]] = mapped_column(String(255), comment="ID склада")
    warehouse_name: Mapped[Optional[str]] = mapped_column(String(255), comment="Название склада")
    stock: Mapped[Optional[int]] = mapped_column(Integer, comment="Остаток без учета резерва")
    reserve: Mapped[Optional[int]] = mapped_column(Integer, comment="Резерв товара")
    quantity: Mapped[Optional[int]] = mapped_column(Integer, comment="Остаток товара")
    cost: Mapped[Optional[float]] = mapped_column(Float, default=0, comment="Себестоимость товара в копейках")



# ---------------------Таблицы для парсера------------------------------

class ParserProductList(Base):
    __tablename__ = "parser_product_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True,
                                    comment="Внутренний ID организации")

    code_ms: Mapped[str] = mapped_column(Text, nullable=False,
                                      comment="Код товара в МС")

    name: Mapped[str] = mapped_column(Text, nullable=False,
                                      comment="Название товара в МС")

    articul: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                               comment="Артикул товара")

    ean: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                               comment="ШК товара")

    pcs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                               comment="ШК товара")

    urls_product: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                               comment="Ссылка на сайт с товаром")


    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения")


class ParserProduct(Base):
    __tablename__ = "parser_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    id_ms: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    code_ms: Mapped[str] = mapped_column(Text, nullable=False)

    name_site: Mapped[str] = mapped_column(Text, nullable=False)

    groupe_site: Mapped[str] = mapped_column(Text, nullable=False)

    articul_site: Mapped[str] = mapped_column(Text, nullable=False)

    url: Mapped[str] = mapped_column(Text, nullable=False)

    images: Mapped[str] = mapped_column(Text, nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    brand: Mapped[str] = mapped_column(Text, nullable=False)

    prices: Mapped[int] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # ------------------------
    # RELATIONS
    # ------------------------

    characteristics: Mapped[List["ParserCharacteristics"]] = relationship(
        "ParserCharacteristics",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    product_images = relationship(
        "WBNormalizedProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        primaryjoin="ParserProduct.id_ms == WBNormalizedProductImage.product_id_ms"
    )

    status_row = relationship(
        "ParserProductStatus",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
        primaryjoin="ParserProduct.id_ms == ParserProductStatus.product_id_ms"
    )


class ParserGroupCharacteristics(Base):
    __tablename__ = "parser_groupe_characteristics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True,
                                    comment="Внутренний ID организации")

    name: Mapped[str] = mapped_column(Text, nullable=False,
                                      comment="Название характеристики")

    domen: Mapped[str] = mapped_column(Text, nullable=False,
                                       comment="С какого сайта")

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения")

    # Связь с характеристиками (один ко многим)
    characteristics: Mapped[List["ParserCharacteristics"]] = relationship(
        "ParserCharacteristics",
        back_populates="group",
        foreign_keys="[ParserCharacteristics.groupe_characteristics]"
    )


class ParserCharacteristics(Base):
    __tablename__ = "parser_characteristics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True,
                                    comment="Внутренний ID организации")

    # Внешний ключ на товар
    product_id_ms: Mapped[str] = mapped_column(
        Text,
        ForeignKey("parser_product.id_ms", ondelete="CASCADE"),
        nullable=False,
        comment="Код ID товара в МС"
    )

    # Внешний ключ на группу характеристик
    groupe_characteristics: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("parser_groupe_characteristics.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID группы характеристики"
    )

    value: Mapped[str] = mapped_column(Text, nullable=False,
                                       comment="Значение характеристики")

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения")

    # Связь с товаром (многие к одному)
    product: Mapped["ParserProduct"] = relationship(
        "ParserProduct",
        back_populates="characteristics",
        foreign_keys=[product_id_ms]
    )

    # Связь с группой характеристик (многие к одному)
    group: Mapped["ParserGroupCharacteristics"] = relationship(
        "ParserGroupCharacteristics",
        back_populates="characteristics",
        foreign_keys=[groupe_characteristics]
    )

#-------------------------Сопоставление данных ВБ

class WBSubjectMapping(Base):
    """Сопоставление категорий сайта с категориями WB"""
    __tablename__ = "wb_subject_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    domain: Mapped[str] = mapped_column(String(100), nullable=False,
                                        comment="Домен сайта")
    site_group: Mapped[str] = mapped_column(String(255), nullable=False,
                                            comment="Группа/категория с сайта")

    subject_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                            comment="ID категории WB")
    subject_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True,
                                                        comment="Название категории WB")

    used_count: Mapped[int] = mapped_column(Integer, default=1,
                                            comment="Сколько раз использовано")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_mapping_domain_group', 'domain', 'site_group'),
        UniqueConstraint('domain', 'site_group', name='uq_domain_site_group'),
    )


class WBNormalizedCharacteristic(Base):
    """Нормализованные характеристики для WB"""
    __tablename__ = "wb_normalized_characteristic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wb_normalized_product.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID нормализованного товара"
    )

    product_id_ms: Mapped[str] = mapped_column(String(255), nullable=False,
                                          comment="ID MS")

    charc_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                          comment="ID характеристики WB")

    charc_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True,
                                                      comment="Название характеристики WB")
    value: Mapped[str] = mapped_column(Text, nullable=False,
                                       comment="Значение характеристики")
    value_type: Mapped[str] = mapped_column(String(20), default="string",
                                            comment="Тип значения: string, number, array")

    # Связь с исходной характеристикой (опционально)
    source_char_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ID исходной характеристики из parser_characteristics"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Связи
    product: Mapped["WBNormalizedProduct"] = relationship(
        "WBNormalizedProduct",
        back_populates="characteristics"
    )


class WBCharacteristicMapping(Base):
    """Сопоставление характеристик сайта с характеристиками WB"""
    __tablename__ = "wb_characteristic_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    domain: Mapped[str] = mapped_column(String(100), nullable=False,
                                        comment="Домен сайта")
    site_characteristic: Mapped[str] = mapped_column(String(255), nullable=False,
                                                     comment="Название характеристики на сайте")
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                            comment="ID категории WB")

    charc_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                          comment="ID характеристики WB")
    charc_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True,
                                                      comment="Название характеристики WB")

    value_transformer: Mapped[str] = mapped_column(String(50), default="direct",
                                                   comment="Трансформатор значения")

    used_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_mapping_domain_char_subject', 'domain', 'site_characteristic', 'subject_id'),
        UniqueConstraint('domain', 'site_characteristic', 'subject_id', name='uq_mapping_full'),
    )


class WBNormalizedProduct(Base):
    """Нормализованные данные товара для загрузки на WB"""
    __tablename__ = "wb_normalized_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Связь с исходным товаром
    product_id_ms: Mapped[str] = mapped_column(
        Text,
        ForeignKey("parser_product.id_ms", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="ID товара из parser_product"
    )

    # Связь с сопоставлением категории
    subject_mapping_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("wb_subject_mapping.id"),
        nullable=True,
        comment="ID сопоставления категории"
    )

    # Категория WB
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                            comment="ID категории WB")
    subject_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True,
                                                        comment="Название категории WB")

    # Основные поля (обязательные для WB)
    vendor_code: Mapped[str] = mapped_column(Text, nullable=False,
                                             comment="Артикул продавца (code_ms)")
    wb_title: Mapped[str] = mapped_column(String(60), nullable=False,
                                          comment="Название для WB (макс 60 символов)")
    wb_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                                          comment="Описание для WB")
    wb_brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True,
                                                    comment="Бренд")
    wb_model: Mapped[Optional[str]] = mapped_column(String(300), nullable=True,
                                                        comment="Артикул товара")

    # Габариты (обязательные для WB)
    length: Mapped[int] = mapped_column(Integer, nullable=True, default=0, comment="Длина (см)")
    width: Mapped[int] = mapped_column(Integer, nullable=True, default=0, comment="Ширина (см)")
    height: Mapped[int] = mapped_column(Integer, nullable=True, default=0, comment="Высота (см)")
    weight: Mapped[float] = mapped_column(Float, nullable=True, default=0.0, comment="Вес (кг)")

    # Статус и метаданные
    status: Mapped[str] = mapped_column(String(50), default="draft",
                                        comment="Статус: draft, ready, uploaded, error")
    wb_nm_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                    comment="Артикул WB (после загрузки)")
    wb_imt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                     comment="ID группы WB")

    # Ошибки
    validation_errors: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                                             comment="Ошибки валидации (JSON)")

    # Временные метки
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                            comment="Дата загрузки на WB")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    subject_mapping: Mapped[Optional["WBSubjectMapping"]] = relationship(
        "WBSubjectMapping",
        foreign_keys=[subject_mapping_id]
    )

    characteristics: Mapped[List["WBNormalizedCharacteristic"]] = relationship(
        "WBNormalizedCharacteristic",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    sizes: Mapped[List["WBNormalizedSize"]] = relationship(
        "WBNormalizedSize",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_normalized_status', 'status'),
        Index('idx_normalized_subject', 'subject_id'),
        Index('idx_normalized_vendor_code', 'vendor_code'),
    )


class WBNormalizedSize(Base):
    """Размеры для WB (цены будут в отдельном модуле)"""
    __tablename__ = "wb_normalized_size"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wb_normalized_product.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID нормализованного товара"
    )

    tech_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True,
                                                     comment="Технический размер (S, M, L, 0)")
    wb_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True,
                                                   comment="Размер WB (42, 44, 46)")
    barcode: Mapped[str] = mapped_column(String(50), nullable=True,
                                         comment="Баркод (SKU)")
    stock: Mapped[int] = mapped_column(Integer, default=0,
                                       comment="Остатки")

    # WB возвращает chrtID после создания
    chrt_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                   comment="ID размера WB")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    product: Mapped["WBNormalizedProduct"] = relationship(
        "WBNormalizedProduct",
        back_populates="sizes"
    )

    __table_args__ = (
        Index('idx_size_barcode', 'barcode'),
        UniqueConstraint('product_id', 'barcode', name='uq_product_barcode'),
    )


class WBSubjectCharacteristic(Base):
    """
    ORM-модель связи «WB Subject ↔ WB Characteristic».

    Назначение:
    - хранит, какие характеристики разрешены/доступны для конкретного subject (категории WB);
    - позволяет помечать обязательность характеристики в рамках subject.

    Используется как mapping-таблица (many-to-many с дополнительным полем is_required).
    """

    __tablename__ = "wb_subject_characteristics"

    # Внутренний PK записи связи
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FK на предмет (категорию) WB
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wb_subject.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID subject (категории) Wildberries"
    )

    # FK на характеристику WB
    wb_characteristic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wb_characteristic.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID характеристики Wildberries"
    )

    # Является ли характеристика обязательной для этого subject
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Признак обязательной характеристики для данного subject"
    )

    # ORM-связи
    subject: Mapped["WBSubject"] = relationship(
        "WBSubject",
        back_populates="subject_characteristics",
        foreign_keys=[subject_id]
    )

    characteristic: Mapped["WBCharacteristic"] = relationship(
        "WBCharacteristic",
        back_populates="subject_links",
        foreign_keys=[wb_characteristic_id]
    )

    __table_args__ = (
        # Защита от дублей одной и той же пары subject + characteristic
        UniqueConstraint(
            "subject_id",
            "wb_characteristic_id",
            name="uq_wb_subject_characteristic_pair"
        ),

        # Индексы для ускорения фильтраций в нормализаторе
        Index("ix_wb_subject_characteristics_subject_id", "subject_id"),
        Index("ix_wb_subject_characteristics_wb_characteristic_id", "wb_characteristic_id"),
    )

# Для загрузки карточек на ВБ
class WBNormalizedProductImage(Base):
    __tablename__ = "wb_normalized_product_image"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # бизнес-ключ связи
    product_id_ms: Mapped[str] = mapped_column(
        Text,
        ForeignKey("parser_product.id_ms", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)

    position: Mapped[int] = mapped_column(Integer, default=0)

    product = relationship(
        "ParserProduct",
        back_populates="product_images",
        primaryjoin="WBNormalizedProductImage.product_id_ms == ParserProduct.id_ms"
    )

class ParserProductStatus(Base):
    __tablename__ = "parser_product_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # бизнес-ключ связи (ВАЖНО)
    product_id_ms: Mapped[str] = mapped_column(
        Text,
        ForeignKey("parser_product.id_ms", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # статус парсинга
    is_parsed: Mapped[bool] = mapped_column(Boolean, default=False)

    is_sent_wb: Mapped[bool] = mapped_column(Boolean, default=False)

    is_error: Mapped[bool] = mapped_column(Boolean, default=False)

    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # связь
    product = relationship(
        "ParserProduct",
        back_populates="status_row",
        primaryjoin="ParserProductStatus.product_id_ms == ParserProduct.id_ms"
    )

class WBStocksForShops(Base):
    __tablename__ = "wb_stocks_for_shops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id_ms: Mapped[str] = mapped_column(String(255), nullable=False, comment="Код МС")
    code_ms: Mapped[str] = mapped_column(String(255), nullable=False, comment="Код МС")
    name_ms: Mapped[Optional[str]] = mapped_column(Text, comment="Наименование МС")
    articul: Mapped[Optional[str]] = mapped_column(Text, comment="Артикул")
    pcs: Mapped[Optional[str]] = mapped_column(Text, comment="Количество поданное магазином")
    comments: Mapped[Optional[str]] = mapped_column(Text, comment="Состояние товара и наличие упаковки")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True,
                                                           comment="Дата и время изменения")

#-----------------GPT------------------

class GPTModels(Base):
    """Модель для хранения информации о доступных GPT моделях"""
    __tablename__ = 'gpt_models'

    # === Основные идентификаторы ===

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        nullable=False,
        comment="Уникальный идентификатор модели (API ключ). Примеры: 'gpt-4o', 'grok-4.1-fast'"
    )
    """Уникальный идентификатор модели. Используется как первичный ключ для быстрого поиска и связей."""

    object: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default='model',
        comment="Тип объекта API. Всегда 'model' для этого типа данных"
    )
    """Служебное поле API, всегда равно 'model'."""

    # === Информация о модели ===

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Человекочитаемое название модели. Пример: 'GPT 4o Vision 128K', 'Grok 4.1 Fast'"
    )
    """Отображаемое название модели для пользовательского интерфейса."""

    created: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Unix timestamp создания модели (секунды с 1970-01-01). Пример: 1685584800"
    )
    """Дата выпуска модели в формате Unix timestamp."""

    # === Технические ограничения ===

    max_capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Максимальная длина контекста в токенах (входные токены). Важно для ограничения размера запроса"
    )
    """Максимальное количество токенов, которое модель может обработать на входе."""

    max_completion_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Максимальное количество токенов в ответе. Может быть NULL для моделей без этого ограничения"
    )
    """Ограничение на длину генерируемого ответа в токенах."""

    # === Цены (в долларах США за 1000 токенов) ===

    cost_context: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Стоимость входного контекста в $ за 1000 токенов. Хранится как строка для сохранения точности"
    )
    """Цена за обработку входных токенов. Формат: строковое представление числа с плавающей точкой."""

    cost_completion: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Стоимость генерации ответа в $ за 1000 токенов. Хранится как строка для сохранения точности"
    )
    """Цена за генерацию выходных токенов."""

    # === Дополнительные атрибуты ===

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default='TEXT',
        comment="Тип модели: TEXT (текстовая), EMBEDDING (эмбеддинги), MODERATION (модерация), VISION (мультимодальная)"
    )
    """Категория модели для классификации и фильтрации."""

    opencode: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Флаг открытой модели (True - открытая модель, False - проприетарная)"
    )
    """Указывает, является ли модель открытой (open-source) или проприетарной."""

    # === Служебные поля ===

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Флаг активности модели. Если False - модель считается устаревшей и не используется"
    )
    """Позволяет временно отключать модели без удаления из базы."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Дата и время добавления записи в БД"
    )
    """Автоматическая метка времени создания записи."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Дата и время последнего обновления записи"
    )
    """Автоматическая метка времени последнего обновления."""

    # === Индексы для оптимизации запросов ===

    __table_args__ = (
        Index('idx_models_type', 'type'),
        Index('idx_models_is_active', 'is_active'),
        Index('idx_models_cost_context', 'cost_context'),
        Index('idx_models_created', 'created'),
        {'comment': 'Таблица для хранения информации о моделях GPTunnel API'}
    )

    # === Связи с другими таблицами (опционально) ===

    # logs: Mapped[List["RequestLog"]] = relationship(back_populates="model")
    """Связь с логами запросов (если есть таблица RequestLog)"""

    # prices: Mapped[List["PriceHistory"]] = relationship(back_populates="model")
    """Связь с историей изменения цен (если нужно отслеживать динамику)"""

    def __repr__(self) -> str:
        """Строковое представление модели для отладки"""
        return f"<Model(id='{self.id}', title='{self.title}', type='{self.type}')>"

    def get_cost_context_float(self) -> float:
        """Получить стоимость контекста как число с плавающей точкой"""
        return float(self.cost_context) if self.cost_context else 0.0

    def get_cost_completion_float(self) -> float:
        """Получить стоимость генерации как число с плавающей точкой"""
        return float(self.cost_completion) if self.cost_completion else 0.0

    def get_created_date(self) -> datetime:
        """Получить дату создания модели как datetime объект"""
        return datetime.fromtimestamp(self.created)

    def is_vision_model(self) -> bool:
        """Проверить, поддерживает ли модель обработку изображений"""
        return 'vision' in self.title.lower() or self.type == 'VISION'

    def is_embedding_model(self) -> bool:
        """Проверить, является ли модель моделью эмбеддингов"""
        return self.type == 'EMBEDDING' or 'embedding' in self.id

class GPTChatLog(Base):
    __tablename__ = "gpt_chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # связь с товаром
    product_id_ms: Mapped[str] = mapped_column(String, index=True)

    # модель
    model: Mapped[str] = mapped_column(String, index=True)

    # ответ модели
    content: Mapped[str] = mapped_column(Text)

    # мета OpenAI-like response
    response_id: Mapped[str] = mapped_column(String, nullable=True)
    object: Mapped[str] = mapped_column(String, nullable=True)
    created: Mapped[int] = mapped_column(BigInteger, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=True)

    # usage
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=True)

    prompt_cost: Mapped[float] = mapped_column(Float, nullable=True)
    completion_cost: Mapped[float] = mapped_column(Float, nullable=True)
    total_cost: Mapped[float] = mapped_column(Float, nullable=True)

    # полный сырой ответ (для дебага)
    raw_response: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[int] = mapped_column(BigInteger, nullable=True)


#----------------Аналитика с ВБ------------------


# Создаем таблицы
Base.metadata.create_all(engine)