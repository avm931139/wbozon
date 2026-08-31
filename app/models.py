from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


class Example(Base):
    __tablename__ = "example"
    __table_args__ = {"comment": "Техническая тестовая таблица для проверки подключения к БД."}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class WBSubject(Base):
    __tablename__ = "wb_subjects"
    __table_args__ = {"comment": "Справочник предметов (категорий товаров) Wildberries."}

    id = Column(Integer, primary_key=True, index=True)
    wb_id = Column(Integer, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    raw_data = Column(JSON, nullable=True)

    products = relationship("WBProduct", back_populates="subject")


class WBProduct(Base):
    __tablename__ = "wb_products"
    __table_args__ = {"comment": "Основные карточки товаров Wildberries."}

    id = Column(Integer, primary_key=True, index=True)
    nm_id = Column(BigInteger, nullable=False, unique=True, index=True)
    imt_id = Column(BigInteger, nullable=True, index=True)
    nm_uuid = Column(String(36), nullable=True, unique=True, index=True)
    subject_id = Column(Integer, ForeignKey("wb_subjects.id"), nullable=True, index=True)
    vendor_code = Column(String, nullable=True, index=True)
    brand = Column(String, nullable=True, index=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    need_kiz = Column(Boolean, nullable=False, default=False)
    kiz_marked = Column(Boolean, nullable=False, default=False)
    wb_created_at = Column(DateTime(timezone=True), nullable=True)
    wb_updated_at = Column(DateTime(timezone=True), nullable=True)
    documents = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    subject = relationship("WBSubject", back_populates="products")
    photos = relationship("WBProductPhoto", back_populates="product", cascade="all, delete-orphan")
    dimensions = relationship(
        "WBProductDimensions",
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )
    characteristic_values = relationship(
        "WBProductCharacteristic",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    sizes = relationship("WBProductSize", back_populates="product", cascade="all, delete-orphan")


class WBProductPhoto(Base):
    __tablename__ = "wb_product_photos"
    __table_args__ = (UniqueConstraint("product_id", "position", name="uq_wb_product_photo_position"), {"comment": "Фотографии карточек товаров Wildberries в порядке отображения."})

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("wb_products.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    big_url = Column(Text, nullable=True)
    c246x328_url = Column(Text, nullable=True)
    c516x688_url = Column(Text, nullable=True)
    hq_url = Column(Text, nullable=True)
    square_url = Column(Text, nullable=True)
    tm_url = Column(Text, nullable=True)

    product = relationship("WBProduct", back_populates="photos")


class WBProductDimensions(Base):
    __tablename__ = "wb_product_dimensions"
    __table_args__ = {"comment": "Габариты и масса упаковки товара Wildberries."}

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("wb_products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    width = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    length = Column(Float, nullable=True)
    weight_brutto = Column(Float, nullable=True)
    is_valid = Column(Boolean, nullable=True)

    product = relationship("WBProduct", back_populates="dimensions")


class WBCharacteristic(Base):
    __tablename__ = "wb_characteristics"
    __table_args__ = {"comment": "Справочник характеристик товаров Wildberries."}

    id = Column(Integer, primary_key=True)
    wb_id = Column(BigInteger, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)

    product_values = relationship("WBProductCharacteristic", back_populates="characteristic")


class WBProductCharacteristic(Base):
    __tablename__ = "wb_product_characteristics"
    __table_args__ = (
        UniqueConstraint("product_id", "characteristic_id", name="uq_wb_product_characteristic"),
        {"comment": "Значения характеристик, назначенные карточкам товаров Wildberries."},
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("wb_products.id", ondelete="CASCADE"), nullable=False, index=True)
    characteristic_id = Column(
        Integer,
        ForeignKey("wb_characteristics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value = Column(JSON, nullable=True)

    product = relationship("WBProduct", back_populates="characteristic_values")
    characteristic = relationship("WBCharacteristic", back_populates="product_values")


class WBProductSize(Base):
    __tablename__ = "wb_product_sizes"
    __table_args__ = {"comment": "Размеры и chrtId товарных карточек Wildberries."}

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("wb_products.id", ondelete="CASCADE"), nullable=False, index=True)
    chrt_id = Column(BigInteger, nullable=False, unique=True, index=True)
    tech_size = Column(String, nullable=True)
    wb_size = Column(String, nullable=True)

    product = relationship("WBProduct", back_populates="sizes")
    barcodes = relationship("WBSizeBarcode", back_populates="size", cascade="all, delete-orphan")
    stocks = relationship("WBFBSStock", back_populates="size")


class WBSizeBarcode(Base):
    __tablename__ = "wb_size_barcodes"
    __table_args__ = {"comment": "Баркоды, связанные с размерами товаров Wildberries."}

    id = Column(Integer, primary_key=True)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id", ondelete="CASCADE"), nullable=False, index=True)
    barcode = Column(String, nullable=False, unique=True, index=True)

    size = relationship("WBProductSize", back_populates="barcodes")


class WBFBSWarehouse(Base):
    __tablename__ = "wb_fbs_warehouses"
    __table_args__ = (
        UniqueConstraint("wb_id", name="uq_wb_fbs_warehouses_wb_id"),
        Index("ix_wb_fbs_warehouses_wb_id", "wb_id"),
        {"comment": "Склады продавца Wildberries для схемы FBS."},
    )

    id = Column(Integer, primary_key=True, index=True)
    wb_id = Column(BigInteger, nullable=False)
    name = Column(String, nullable=True)
    office_id = Column(BigInteger, nullable=True)
    cargo_type = Column(Integer, nullable=True)
    delivery_type = Column(Integer, nullable=True)
    is_deleting = Column(Boolean, nullable=True)
    is_processing = Column(Boolean, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    stocks = relationship("WBFBSStock", back_populates="warehouse", cascade="all, delete-orphan")


class WBFBSStock(Base):
    __tablename__ = "wb_fbs_stocks"
    __table_args__ = (
        UniqueConstraint("sku", "warehouse_id", name="uq_wb_fbs_stocks_sku_warehouse"),
        {"comment": "Текущие остатки товаров на складах продавца по схеме FBS."},
    )

    id = Column(Integer, primary_key=True, index=True)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("wb_fbs_warehouses.id"), nullable=False, index=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    size = relationship("WBProductSize", back_populates="stocks")
    warehouse = relationship("WBFBSWarehouse", back_populates="stocks")


class WBFboWarehouse(Base):
    __tablename__ = "wb_fbo_warehouses"
    __table_args__ = (
        UniqueConstraint("wb_id", "name", "region_name", name="uq_wb_fbo_warehouse_identity"),
        {"comment": "Склады Wildberries для схемы FBO с региональной принадлежностью."},
    )

    id = Column(Integer, primary_key=True, index=True)
    wb_id = Column(BigInteger, nullable=False, index=True)
    name = Column(String, nullable=False)
    region_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    stocks = relationship("WBFboStock", back_populates="warehouse", cascade="all, delete-orphan")


class WBFboStock(Base):
    __tablename__ = "wb_fbo_stocks"
    __table_args__ = (
        UniqueConstraint("size_id", "warehouse_id", name="uq_wb_fbo_stocks_size_warehouse"),
        {"comment": "Остатки и товары в пути на складах Wildberries по схеме FBO."},
    )

    id = Column(Integer, primary_key=True, index=True)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("wb_fbo_warehouses.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    in_way_to_client = Column(Integer, nullable=False, default=0)
    in_way_from_client = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    size = relationship("WBProductSize")
    warehouse = relationship("WBFboWarehouse", back_populates="stocks")


class WBFBSStockSnapshot(Base):
    __tablename__ = "wb_fbs_stock_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "sku", "warehouse_id", name="uq_wb_fbs_stock_snapshot"),
        {"comment": "Ежедневные срезы FBS-остатков Wildberries на 00:00 по Москве."},
    )

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("wb_fbs_warehouses.id"), nullable=False, index=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=True)


class WBFboStockSnapshot(Base):
    __tablename__ = "wb_fbo_stock_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "size_id", "warehouse_id", name="uq_wb_fbo_stock_snapshot"),
        {"comment": "Ежедневные срезы FBO-остатков Wildberries на 00:00 по Москве."},
    )

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("wb_fbo_warehouses.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    in_way_to_client = Column(Integer, nullable=False, default=0)
    in_way_from_client = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=True)


class WBFBSOrder(Base):
    __tablename__ = "wb_fbs_orders"
    __table_args__ = {"comment": "Заказы Wildberries, обрабатываемые продавцом по схеме FBS."}

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(BigInteger, nullable=False, unique=True, index=True)
    order_uid = Column(String, nullable=True, index=True)
    rid = Column(String, nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("wb_fbs_warehouses.id"), nullable=True, index=True)
    warehouse_wb_id = Column(BigInteger, nullable=True, index=True)
    office_id = Column(BigInteger, nullable=True)
    created_at_wb = Column(DateTime(timezone=True), nullable=False, index=True)
    supply_id = Column(String, nullable=True, index=True)
    delivery_type = Column(String, nullable=True)
    article = Column(String, nullable=True)
    color_code = Column(String, nullable=True)
    skus = Column(JSON, nullable=True)
    price = Column(BigInteger, nullable=True)
    scan_price = Column(BigInteger, nullable=True)
    converted_price = Column(BigInteger, nullable=True)
    currency_code = Column(Integer, nullable=True)
    converted_currency_code = Column(Integer, nullable=True)
    cargo_type = Column(Integer, nullable=True)
    cross_border_type = Column(Integer, nullable=True)
    is_zero_order = Column(Boolean, nullable=False, default=False)
    is_b2b = Column(Boolean, nullable=False, default=False)
    supplier_status = Column(String, nullable=True, index=True)
    wb_status = Column(String, nullable=True, index=True)
    address = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WBFboOrder(Base):
    __tablename__ = "wb_fbo_orders"
    __table_args__ = {"comment": "История заказов Wildberries, исполненных со складов WB по схеме FBO."}

    id = Column(Integer, primary_key=True, index=True)
    srid = Column(String, nullable=False, unique=True, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=True, index=True)
    order_date = Column(DateTime, nullable=False, index=True)
    last_change_date = Column(DateTime, nullable=False, index=True)
    warehouse_name = Column(String, nullable=True, index=True)
    warehouse_type = Column(String, nullable=True, index=True)
    country_name = Column(String, nullable=True)
    federal_district_name = Column(String, nullable=True)
    region_name = Column(String, nullable=True)
    supplier_article = Column(String, nullable=True, index=True)
    barcode = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    tech_size = Column(String, nullable=True)
    income_id = Column(BigInteger, nullable=True)
    is_supply = Column(Boolean, nullable=False, default=False)
    is_realization = Column(Boolean, nullable=False, default=False)
    total_price = Column(Float, nullable=True)
    discount_percent = Column(Float, nullable=True)
    spp = Column(Float, nullable=True)
    finished_price = Column(Float, nullable=True)
    price_with_discount = Column(Float, nullable=True)
    is_cancel = Column(Boolean, nullable=False, default=False, index=True)
    cancel_date = Column(DateTime, nullable=True)
    sticker = Column(String, nullable=True)
    g_number = Column(String, nullable=True, index=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WBFbwWarehouse(Base):
    __tablename__ = "wb_fbw_warehouses"
    __table_args__ = {"comment": "Справочник складов Wildberries, доступных для поставок FBW."}

    id = Column(Integer, primary_key=True, index=True)
    wb_id = Column(BigInteger, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    address = Column(Text, nullable=True)
    work_time = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    is_transit_active = Column(Boolean, nullable=False, default=False)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WBFbwSupply(Base):
    __tablename__ = "wb_fbw_supplies"
    __table_args__ = {"comment": "Поставки и предварительные поставки продавца на склады Wildberries (FBW)."}

    id = Column(Integer, primary_key=True, index=True)
    supply_wb_id = Column(BigInteger, nullable=True, unique=True, index=True)
    preorder_wb_id = Column(BigInteger, nullable=True, unique=True, index=True)
    status_id = Column(Integer, nullable=False, index=True)
    box_type_id = Column(Integer, nullable=True)
    virtual_type_id = Column(Integer, nullable=True)
    is_box_on_pallet = Column(Boolean, nullable=True)
    create_date = Column(DateTime(timezone=True), nullable=False, index=True)
    supply_date = Column(DateTime(timezone=True), nullable=True, index=True)
    fact_date = Column(DateTime(timezone=True), nullable=True, index=True)
    source_updated_date = Column(DateTime(timezone=True), nullable=True, index=True)
    warehouse_wb_id = Column(BigInteger, nullable=True, index=True)
    warehouse_name = Column(String, nullable=True)
    actual_warehouse_wb_id = Column(BigInteger, nullable=True)
    actual_warehouse_name = Column(String, nullable=True)
    transit_warehouse_wb_id = Column(BigInteger, nullable=True)
    transit_warehouse_name = Column(String, nullable=True)
    acceptance_cost = Column(Float, nullable=True)
    paid_acceptance_coefficient = Column(Float, nullable=True)
    storage_coefficient = Column(String, nullable=True)
    delivery_coefficient = Column(String, nullable=True)
    reject_reason = Column(Text, nullable=True)
    supplier_assign_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    accepted_quantity = Column(Integer, nullable=True)
    ready_for_sale_quantity = Column(Integer, nullable=True)
    unloading_quantity = Column(Integer, nullable=True)
    depersonalized_quantity = Column(Integer, nullable=True)
    can_show_quantity = Column(Boolean, nullable=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    goods = relationship("WBFbwSupplyGood", back_populates="supply", cascade="all, delete-orphan")
    packages = relationship("WBFbwSupplyPackage", back_populates="supply", cascade="all, delete-orphan")
    snapshots = relationship("WBFbwSupplySnapshot", back_populates="supply", cascade="all, delete-orphan")


class WBFbwSupplyGood(Base):
    __tablename__ = "wb_fbw_supply_goods"
    __table_args__ = (UniqueConstraint("supply_id", "barcode", name="uq_wb_fbw_supply_good_barcode"), {"comment": "Товарные позиции и количества внутри поставок FBW."})

    id = Column(Integer, primary_key=True, index=True)
    supply_id = Column(Integer, ForeignKey("wb_fbw_supplies.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    size_id = Column(Integer, ForeignKey("wb_product_sizes.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=False, index=True)
    barcode = Column(String, nullable=False, index=True)
    vendor_code = Column(String, nullable=True)
    tech_size = Column(String, nullable=True)
    color = Column(String, nullable=True)
    tnved = Column(String, nullable=True)
    need_kiz = Column(Boolean, nullable=False, default=False)
    supplier_box_amount = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    accepted_quantity = Column(Integer, nullable=False, default=0)
    ready_for_sale_quantity = Column(Integer, nullable=False, default=0)
    unloading_quantity = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)

    supply = relationship("WBFbwSupply", back_populates="goods")


class WBFbwSupplyPackage(Base):
    __tablename__ = "wb_fbw_supply_packages"
    __table_args__ = (UniqueConstraint("supply_id", "package_code", name="uq_wb_fbw_supply_package_code"), {"comment": "Короба, палеты и другие упаковки поставок FBW."})

    id = Column(Integer, primary_key=True, index=True)
    supply_id = Column(Integer, ForeignKey("wb_fbw_supplies.id", ondelete="CASCADE"), nullable=False, index=True)
    package_code = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)

    supply = relationship("WBFbwSupply", back_populates="packages")
    goods = relationship("WBFbwSupplyPackageGood", back_populates="package", cascade="all, delete-orphan")


class WBFbwSupplyPackageGood(Base):
    __tablename__ = "wb_fbw_supply_package_goods"
    __table_args__ = (UniqueConstraint("package_id", "barcode", name="uq_wb_fbw_package_good_barcode"), {"comment": "Распределение товарных баркодов по упаковкам поставки FBW."})

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("wb_fbw_supply_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    barcode = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)

    package = relationship("WBFbwSupplyPackage", back_populates="goods")


class WBFbwSupplySnapshot(Base):
    __tablename__ = "wb_fbw_supply_snapshots"
    __table_args__ = (UniqueConstraint("supply_id", "source_updated_date", name="uq_wb_fbw_supply_snapshot_version"), {"comment": "История состояний и количественных показателей поставок FBW."})

    id = Column(Integer, primary_key=True, index=True)
    supply_id = Column(Integer, ForeignKey("wb_fbw_supplies.id", ondelete="CASCADE"), nullable=False, index=True)
    source_updated_date = Column(DateTime(timezone=True), nullable=False)
    status_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=True)
    accepted_quantity = Column(Integer, nullable=True)
    ready_for_sale_quantity = Column(Integer, nullable=True)
    unloading_quantity = Column(Integer, nullable=True)
    depersonalized_quantity = Column(Integer, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_data = Column(JSON, nullable=False)

    supply = relationship("WBFbwSupply", back_populates="snapshots")


class WBFinancialSalesReport(Base):
    __tablename__ = "wb_financial_sales_reports"
    __table_args__ = {"comment": "Сводные финансовые отчёты Wildberries о продажах и реализации."}

    id = Column(Integer, primary_key=True, index=True)
    report_wb_id = Column(BigInteger, nullable=False, unique=True, index=True)
    seller_finance_name = Column(String, nullable=True)
    date_from = Column(DateTime(timezone=True), nullable=False, index=True)
    date_to = Column(DateTime(timezone=True), nullable=False, index=True)
    create_date = Column(DateTime(timezone=True), nullable=False, index=True)
    currency = Column(String, nullable=False)
    report_type = Column(Integer, nullable=False, index=True)
    retail_amount_sum = Column(Numeric(20, 6), nullable=False, default=0)
    for_pay_sum = Column(Numeric(20, 6), nullable=False, default=0)
    delivery_service_sum = Column(Numeric(20, 6), nullable=False, default=0)
    paid_storage_sum = Column(Numeric(20, 6), nullable=False, default=0)
    paid_acceptance_sum = Column(Numeric(20, 6), nullable=False, default=0)
    deduction_sum = Column(Numeric(20, 6), nullable=False, default=0)
    penalty_sum = Column(Numeric(20, 6), nullable=False, default=0)
    additional_payment_sum = Column(Numeric(20, 6), nullable=False, default=0)
    bank_payment_sum = Column(Numeric(20, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    details_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    rows = relationship("WBFinancialSalesRow", back_populates="report", cascade="all, delete-orphan")


class WBFinancialSalesRow(Base):
    __tablename__ = "wb_financial_sales_rows"
    __table_args__ = {"comment": "Детализированные финансовые операции отчётов реализации Wildberries."}

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("wb_financial_sales_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    rrd_id = Column(BigInteger, nullable=False, unique=True, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=True, index=True)
    order_id = Column(BigInteger, nullable=True, index=True)
    order_uid = Column(String, nullable=True, index=True)
    srid = Column(String, nullable=True, index=True)
    shk_id = Column(BigInteger, nullable=True)
    sku = Column(String, nullable=True, index=True)
    vendor_code = Column(String, nullable=True)
    title = Column(String, nullable=True)
    subject_name = Column(String, nullable=True)
    brand_name = Column(String, nullable=True)
    tech_size = Column(String, nullable=True)
    seller_operation_name = Column(String, nullable=True, index=True)
    order_date = Column(DateTime(timezone=True), nullable=True, index=True)
    sale_date = Column(DateTime(timezone=True), nullable=True, index=True)
    rr_date = Column(DateTime(timezone=True), nullable=True, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    retail_price = Column(Numeric(20, 6), nullable=False, default=0)
    retail_amount = Column(Numeric(20, 6), nullable=False, default=0)
    retail_price_with_discount = Column(Numeric(20, 6), nullable=False, default=0)
    for_pay = Column(Numeric(20, 6), nullable=False, default=0)
    delivery_service = Column(Numeric(20, 6), nullable=False, default=0)
    acquiring_fee = Column(Numeric(20, 6), nullable=False, default=0)
    ppvz_sales_commission = Column(Numeric(20, 6), nullable=False, default=0)
    ppvz_reward = Column(Numeric(20, 6), nullable=False, default=0)
    penalty = Column(Numeric(20, 6), nullable=False, default=0)
    additional_payment = Column(Numeric(20, 6), nullable=False, default=0)
    rebill_logistic_cost = Column(Numeric(20, 6), nullable=False, default=0)
    paid_storage = Column(Numeric(20, 6), nullable=False, default=0)
    deduction = Column(Numeric(20, 6), nullable=False, default=0)
    paid_acceptance = Column(Numeric(20, 6), nullable=False, default=0)
    currency = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=False)

    report = relationship("WBFinancialSalesReport", back_populates="rows")


class WBFinancialAcquiringReport(Base):
    __tablename__ = "wb_financial_acquiring_reports"
    __table_args__ = {"comment": "Сводные отчёты Wildberries об издержках на приём платежей."}

    id = Column(Integer, primary_key=True, index=True)
    report_wb_id = Column(BigInteger, nullable=False, unique=True, index=True)
    seller_finance_name = Column(String, nullable=True)
    date_from = Column(DateTime(timezone=True), nullable=False, index=True)
    date_to = Column(DateTime(timezone=True), nullable=False, index=True)
    create_date = Column(DateTime(timezone=True), nullable=False, index=True)
    currency = Column(String, nullable=False)
    acquiring_fee_sum = Column(Numeric(20, 6), nullable=False, default=0)
    acquiring_fee_vat_sum = Column(Numeric(20, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    details_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    rows = relationship("WBFinancialAcquiringRow", back_populates="report", cascade="all, delete-orphan")


class WBFinancialAcquiringRow(Base):
    __tablename__ = "wb_financial_acquiring_rows"
    __table_args__ = {"comment": "Детализация эквайринга Wildberries с исходными и знаковыми суммами операций."}

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("wb_financial_acquiring_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    rrd_id = Column(BigInteger, nullable=False, unique=True, index=True)
    nm_id = Column(BigInteger, nullable=True, index=True)
    srid = Column(String, nullable=True, index=True)
    shk_id = Column(BigInteger, nullable=True)
    acquiring_bank = Column(String, nullable=True)
    document_type = Column(String, nullable=True)
    operation_sign = Column(Integer, nullable=False, default=1)
    invoice_number = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    retail_amount = Column(Numeric(20, 6), nullable=False, default=0)
    signed_retail_amount = Column(Numeric(20, 6), nullable=False, default=0)
    acquiring_fee = Column(Numeric(20, 6), nullable=False, default=0)
    signed_acquiring_fee = Column(Numeric(20, 6), nullable=False, default=0)
    acquiring_fee_vat = Column(Numeric(20, 6), nullable=False, default=0)
    signed_acquiring_fee_vat = Column(Numeric(20, 6), nullable=False, default=0)
    transaction_date = Column(DateTime(timezone=True), nullable=True, index=True)
    sale_date = Column(DateTime(timezone=True), nullable=True, index=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    raw_data = Column(JSON, nullable=False)

    report = relationship("WBFinancialAcquiringReport", back_populates="rows")


class WBCustomerQuestion(Base):
    __tablename__ = "wb_customer_questions"
    __table_args__ = {"comment": "Вопросы покупателей Wildberries и метрики качества ответа продавца."}

    id = Column(Integer, primary_key=True, index=True)
    question_wb_id = Column(String, nullable=False, unique=True, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=True, index=True)
    imt_id = Column(BigInteger, nullable=True)
    text = Column(Text, nullable=False)
    state = Column(String, nullable=True, index=True)
    was_viewed = Column(Boolean, nullable=False, default=False)
    is_warned = Column(Boolean, nullable=False, default=False)
    is_processed = Column(Boolean, nullable=False, default=False, index=True)
    is_answered = Column(Boolean, nullable=False, default=False, index=True)
    created_date = Column(DateTime(timezone=True), nullable=False, index=True)
    answer_text = Column(Text, nullable=True)
    answer_created_date = Column(DateTime(timezone=True), nullable=True, index=True)
    answer_editable = Column(Boolean, nullable=True)
    response_seconds = Column(BigInteger, nullable=True)
    sla_hours = Column(Integer, nullable=False)
    sla_breached = Column(Boolean, nullable=False, default=False, index=True)
    answer_quality_score = Column(Integer, nullable=True, index=True)
    product_name = Column(String, nullable=True)
    supplier_article = Column(String, nullable=True)
    brand_name = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    answer_versions = relationship("WBCustomerQuestionAnswer", back_populates="question", cascade="all, delete-orphan")


class WBCustomerQuestionAnswer(Base):
    __tablename__ = "wb_customer_question_answers"
    __table_args__ = (
        UniqueConstraint("question_id", "answer_created_date", "text", name="uq_wb_question_answer_version"),
        {"comment": "История полученных из WB версий ответов продавца на вопросы покупателей."},
    )

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("wb_customer_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    answer_created_date = Column(DateTime(timezone=True), nullable=True)
    editable = Column(Boolean, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("WBCustomerQuestion", back_populates="answer_versions")


class WBCustomerFeedback(Base):
    __tablename__ = "wb_customer_feedbacks"
    __table_args__ = {"comment": "Отзывы покупателей Wildberries, оценки товара и метрики ответа продавца."}

    id = Column(Integer, primary_key=True, index=True)
    feedback_wb_id = Column(String, nullable=False, unique=True, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=True, index=True)
    imt_id = Column(BigInteger, nullable=True)
    parent_feedback_wb_id = Column(String, nullable=True)
    child_feedback_wb_id = Column(String, nullable=True)
    text = Column(Text, nullable=False, default="")
    pros = Column(Text, nullable=False, default="")
    cons = Column(Text, nullable=False, default="")
    product_valuation = Column(Integer, nullable=False, index=True)
    user_name = Column(String, nullable=True)
    state = Column(String, nullable=True, index=True)
    order_status = Column(String, nullable=True)
    was_viewed = Column(Boolean, nullable=False, default=False)
    is_processed = Column(Boolean, nullable=False, default=False, index=True)
    is_answerable = Column(Boolean, nullable=False, default=False, index=True)
    is_answered = Column(Boolean, nullable=False, default=False, index=True)
    created_date = Column(DateTime(timezone=True), nullable=False, index=True)
    answer_text = Column(Text, nullable=True)
    answer_created_date = Column(DateTime(timezone=True), nullable=True, index=True)
    answer_editable = Column(Boolean, nullable=True)
    response_seconds = Column(BigInteger, nullable=True)
    sla_hours = Column(Integer, nullable=False)
    sla_breached = Column(Boolean, nullable=False, default=False, index=True)
    answer_quality_score = Column(Integer, nullable=True, index=True)
    product_name = Column(String, nullable=True)
    supplier_article = Column(String, nullable=True)
    brand_name = Column(String, nullable=True)
    subject_id = Column(BigInteger, nullable=True)
    subject_name = Column(String, nullable=True)
    color = Column(String, nullable=True)
    photo_links = Column(JSON, nullable=True)
    video = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    last_order_shk_id = Column(BigInteger, nullable=True)
    last_order_created_at = Column(DateTime(timezone=True), nullable=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    answer_versions = relationship("WBCustomerFeedbackAnswer", back_populates="feedback", cascade="all, delete-orphan")


class WBCustomerFeedbackAnswer(Base):
    __tablename__ = "wb_customer_feedback_answers"
    __table_args__ = (
        UniqueConstraint("feedback_id", "answer_created_date", "text", name="uq_wb_feedback_answer_version"),
        {"comment": "История полученных из WB версий ответов продавца на отзывы покупателей."},
    )

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("wb_customer_feedbacks.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    answer_created_date = Column(DateTime(timezone=True), nullable=True)
    editable = Column(Boolean, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    feedback = relationship("WBCustomerFeedback", back_populates="answer_versions")


class WBAdvertCampaign(Base):
    __tablename__ = "wb_advert_campaigns"
    __table_args__ = {"comment": "Рекламные кампании WB Продвижение и их последнее известное состояние."}

    id = Column(Integer, primary_key=True, index=True)
    advert_wb_id = Column(BigInteger, nullable=False, unique=True, index=True)
    name = Column(String, nullable=True)
    advert_type = Column(Integer, nullable=True, index=True)
    status = Column(Integer, nullable=True, index=True)
    change_time = Column(DateTime(timezone=True), nullable=True, index=True)
    budget_cash = Column(Numeric(20, 6), nullable=True)
    budget_netting = Column(Numeric(20, 6), nullable=True)
    budget_total = Column(Numeric(20, 6), nullable=True)
    budget_fetched_at = Column(DateTime, nullable=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    expenses = relationship("WBAdvertExpense", back_populates="campaign")
    daily_stats = relationship("WBAdvertDailyStat", back_populates="campaign", cascade="all, delete-orphan")


class WBPromotionAccountSnapshot(Base):
    __tablename__ = "wb_promotion_account_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    balance = Column(Numeric(20, 6), nullable=False, default=0)
    net = Column(Numeric(20, 6), nullable=False, default=0)
    bonus = Column(Numeric(20, 6), nullable=False, default=0)
    cashbacks = Column(JSON, nullable=False)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class WBPromotionPayment(Base):
    __tablename__ = "wb_promotion_payments"

    id = Column(Integer, primary_key=True, index=True)
    source_hash = Column(String(64), nullable=False, unique=True, index=True)
    payment_time = Column(DateTime(timezone=True), nullable=True, index=True)
    amount = Column(Numeric(20, 6), nullable=False, default=0)
    payment_type = Column(String, nullable=True, index=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WBSyncRun(Base):
    __tablename__ = "wb_sync_runs"

    id = Column(String(32), primary_key=True)
    status = Column(String(20), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True, index=True)
    duration_seconds = Column(Numeric(20, 3), nullable=True)
    tasks_total = Column(Integer, nullable=False, default=0)
    tasks_succeeded = Column(Integer, nullable=False, default=0)
    tasks_failed = Column(Integer, nullable=False, default=0)
    results = Column(JSON, nullable=False, default=dict)

    errors = relationship("WBSyncError", back_populates="run", cascade="all, delete-orphan")


class WBSyncError(Base):
    __tablename__ = "wb_sync_errors"

    id = Column(BigInteger, primary_key=True)
    cycle_id = Column(String(32), ForeignKey("wb_sync_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    task = Column(String(100), nullable=True, index=True)
    phase = Column(String(50), nullable=False, index=True)
    exception_type = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    file = Column(Text, nullable=True)
    line = Column(Integer, nullable=True)
    function = Column(String(255), nullable=True)
    module = Column(String(255), nullable=True)
    source_line = Column(Text, nullable=True)
    traceback = Column(Text, nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)

    run = relationship("WBSyncRun", back_populates="errors")


class WBOperationalOrder(Base):
    __tablename__ = "wb_operational_orders"

    id = Column(BigInteger, primary_key=True)
    srid = Column(String, nullable=False, unique=True, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=True, index=True)
    order_date = Column(DateTime(timezone=True), nullable=False, index=True)
    last_change_date = Column(DateTime(timezone=True), nullable=False, index=True)
    cancel_date = Column(DateTime(timezone=True), nullable=True, index=True)
    is_cancel = Column(Boolean, nullable=False, default=False, index=True)
    warehouse_name = Column(String, nullable=True)
    warehouse_type = Column(String, nullable=True, index=True)
    supplier_article = Column(String, nullable=True, index=True)
    barcode = Column(String, nullable=True, index=True)
    finished_price = Column(Numeric(20, 6), nullable=False, default=0)
    price_with_discount = Column(Numeric(20, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WBOperationalSale(Base):
    __tablename__ = "wb_operational_sales"

    id = Column(BigInteger, primary_key=True)
    sale_id = Column(String, nullable=False, unique=True, index=True)
    srid = Column(String, nullable=False, index=True)
    operation_type = Column(String(20), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=True, index=True)
    event_date = Column(DateTime(timezone=True), nullable=False, index=True)
    last_change_date = Column(DateTime(timezone=True), nullable=False, index=True)
    warehouse_name = Column(String, nullable=True)
    warehouse_type = Column(String, nullable=True, index=True)
    supplier_article = Column(String, nullable=True, index=True)
    barcode = Column(String, nullable=True, index=True)
    finished_price = Column(Numeric(20, 6), nullable=False, default=0)
    price_with_discount = Column(Numeric(20, 6), nullable=False, default=0)
    for_pay = Column(Numeric(20, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WBTelegramDelivery(Base):
    """Durable delivery ledger preventing duplicate group reports."""

    __tablename__ = "wb_telegram_deliveries"

    id = Column(BigInteger, primary_key=True)
    report_key = Column(String(100), nullable=False, unique=True, index=True)
    report_type = Column(String(30), nullable=False, index=True)
    chat_id = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    message_hash = Column(String(64), nullable=True)
    telegram_message_ids = Column(JSON, nullable=False, default=list)
    error_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)


class OperationsMonitorState(Base):
    """Durable discovery cursor for private operational notifications."""

    __tablename__ = "operations_monitor_states"

    id = Column(String(30), primary_key=True)
    cursor_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class OperationsEventDelivery(Base):
    """One durable, deduplicated operational event awaiting a private digest."""

    __tablename__ = "operations_event_deliveries"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_operations_event_delivery_key"),
        {"comment": "Очередь личных Telegram-уведомлений о работе приложения."},
    )

    id = Column(Integer, primary_key=True)
    event_key = Column(String(150), nullable=False, index=True)
    source_type = Column(String(30), nullable=False, index=True)
    source_id = Column(String(100), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    detail = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    telegram_message_ids = Column(JSON, nullable=False, default=list)
    error_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)


class HealthcheckRun(Base):
    """Health state journal used to notify only on failures and recovery."""

    __tablename__ = "healthcheck_runs"

    id = Column(String(32), primary_key=True)
    checked_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    checks_total = Column(Integer, nullable=False)
    checks_failed = Column(Integer, nullable=False)
    failure_signature = Column(String(16), nullable=True, index=True)
    checks = Column(JSON, nullable=False, default=list)


class WBAdvertExpense(Base):
    __tablename__ = "wb_advert_expenses"
    __table_args__ = (
        UniqueConstraint("source_hash", name="uq_wb_advert_expense_source_hash"),
        {"comment": "Фактические списания средств на рекламные кампании из истории затрат WB."},
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("wb_advert_campaigns.id"), nullable=True, index=True)
    upd_num = Column(BigInteger, nullable=True, index=True)
    source_hash = Column(String(64), nullable=False, index=True)
    expense_time = Column(DateTime(timezone=True), nullable=True, index=True)
    amount = Column(Numeric(20, 6), nullable=False)
    currency = Column(String, nullable=False)
    payment_type = Column(String, nullable=True, index=True)
    advert_type = Column(Integer, nullable=True)
    advert_status = Column(Integer, nullable=True)
    campaign_name = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("WBAdvertCampaign", back_populates="expenses")


class WBAdvertDailyStat(Base):
    __tablename__ = "wb_advert_daily_stats"
    __table_args__ = (
        UniqueConstraint("campaign_id", "stat_date", name="uq_wb_advert_daily_stat"),
        {"comment": "Контрольные дневные показатели рекламной кампании WB."},
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("wb_advert_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    stat_date = Column(DateTime(timezone=True), nullable=False, index=True)
    views = Column(BigInteger, nullable=False, default=0)
    clicks = Column(BigInteger, nullable=False, default=0)
    atbs = Column(BigInteger, nullable=False, default=0)
    orders = Column(BigInteger, nullable=False, default=0)
    canceled = Column(BigInteger, nullable=False, default=0)
    shks = Column(BigInteger, nullable=False, default=0)
    spend = Column(Numeric(20, 6), nullable=False, default=0)
    order_sum = Column(Numeric(20, 6), nullable=False, default=0)
    ctr = Column(Numeric(12, 6), nullable=False, default=0)
    cpc = Column(Numeric(20, 6), nullable=False, default=0)
    cr = Column(Numeric(12, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    campaign = relationship("WBAdvertCampaign", back_populates="daily_stats")
    product_stats = relationship("WBAdvertProductDailyStat", back_populates="daily_stat", cascade="all, delete-orphan")


class WBAdvertProductDailyStat(Base):
    __tablename__ = "wb_advert_product_daily_stats"
    __table_args__ = (
        UniqueConstraint("daily_stat_id", "app_type", "nm_id", name="uq_wb_advert_product_daily_stat"),
        {"comment": "Дневная рекламная статистика WB в разрезе площадки и товара nmId."},
    )

    id = Column(Integer, primary_key=True, index=True)
    daily_stat_id = Column(Integer, ForeignKey("wb_advert_daily_stats.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("wb_products.id"), nullable=True, index=True)
    nm_id = Column(BigInteger, nullable=False, index=True)
    app_type = Column(Integer, nullable=False, index=True)
    product_name = Column(String, nullable=True)
    views = Column(BigInteger, nullable=False, default=0)
    clicks = Column(BigInteger, nullable=False, default=0)
    atbs = Column(BigInteger, nullable=False, default=0)
    orders = Column(BigInteger, nullable=False, default=0)
    canceled = Column(BigInteger, nullable=False, default=0)
    shks = Column(BigInteger, nullable=False, default=0)
    spend = Column(Numeric(20, 6), nullable=False, default=0)
    order_sum = Column(Numeric(20, 6), nullable=False, default=0)
    ctr = Column(Numeric(12, 6), nullable=False, default=0)
    cpc = Column(Numeric(20, 6), nullable=False, default=0)
    cr = Column(Numeric(12, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)

    daily_stat = relationship("WBAdvertDailyStat", back_populates="product_stats")


class OzonProduct(Base):
    __tablename__ = "ozon_products"
    __table_args__ = {"comment": "Товары кабинета Ozon Seller."}

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(BigInteger, nullable=False, unique=True, index=True)
    offer_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=True)
    sku = Column(BigInteger, nullable=True, index=True)
    barcode = Column(String, nullable=True, index=True)
    status = Column(String, nullable=True, index=True)
    visibility = Column(String, nullable=True, index=True)
    price = Column(Numeric(20, 6), nullable=True)
    old_price = Column(Numeric(20, 6), nullable=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class OzonStock(Base):
    __tablename__ = "ozon_stocks"
    __table_args__ = (
        UniqueConstraint("product_id", "stock_type", name="uq_ozon_stock_product_type"),
        {"comment": "Текущие остатки товаров Ozon по схеме хранения."},
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(String, nullable=True, index=True)
    stock_type = Column(String, nullable=False, index=True)
    present = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonStockSnapshot(Base):
    __tablename__ = "ozon_stock_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "product_id", "stock_type", name="uq_ozon_stock_snapshot"),
        {"comment": "Ежедневные срезы остатков Ozon на 00:00 по Москве."},
    )

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    product_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(String, nullable=True, index=True)
    stock_type = Column(String, nullable=False, index=True)
    present = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)


class OzonWarehouse(Base):
    __tablename__ = "ozon_warehouses"
    __table_args__ = {
        "comment": "Справочник физических складов Ozon для остатков FBO/FBS."
    }

    id = Column(Integer, primary_key=True, index=True)
    ozon_warehouse_id = Column(BigInteger, nullable=False, unique=True, index=True)
    name = Column(String, nullable=True)
    cluster_id = Column(BigInteger, nullable=True, index=True)
    cluster_name = Column(String, nullable=True)
    macrolocal_cluster_id = Column(BigInteger, nullable=True, index=True)
    stock_types = Column(JSON, nullable=False, default=list)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OzonWarehouseStock(Base):
    __tablename__ = "ozon_warehouse_stocks"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "warehouse_id",
            "stock_type",
            name="uq_ozon_warehouse_stock_identity",
        ),
        {"comment": "Текущие остатки Ozon в разрезе физического склада и схемы хранения."},
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(String, nullable=True, index=True)
    sku = Column(BigInteger, nullable=False, index=True)
    warehouse_id = Column(
        Integer,
        ForeignKey("ozon_warehouses.id"),
        nullable=False,
        index=True,
    )
    stock_type = Column(String, nullable=False, index=True)
    present = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonWarehouseStockSnapshot(Base):
    __tablename__ = "ozon_warehouse_stock_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "product_id",
            "warehouse_id",
            "stock_type",
            name="uq_ozon_warehouse_stock_snapshot",
        ),
        {"comment": "Ежедневные срезы складских остатков Ozon на 00:00 по Москве."},
    )

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    product_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(String, nullable=True, index=True)
    sku = Column(BigInteger, nullable=False, index=True)
    warehouse_id = Column(
        Integer,
        ForeignKey("ozon_warehouses.id"),
        nullable=False,
        index=True,
    )
    stock_type = Column(String, nullable=False, index=True)
    present = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)


class YandexMarketStock(Base):
    __tablename__ = "yandex_market_stocks"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "warehouse_id",
            "offer_id",
            "stock_type",
            name="uq_yandex_market_stock_identity",
        ),
        {"comment": "Текущие остатки Яндекс Маркета по магазину, складу, SKU и типу."},
    )

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(BigInteger, nullable=False, index=True)
    warehouse_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(String, nullable=False, index=True)
    stock_type = Column(String, nullable=False, index=True)
    count = Column(Integer, nullable=False, default=0)
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class YandexMarketStockSnapshot(Base):
    __tablename__ = "yandex_market_stock_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "campaign_id",
            "warehouse_id",
            "offer_id",
            "stock_type",
            name="uq_yandex_market_stock_snapshot",
        ),
        {"comment": "Ежедневные срезы остатков Яндекс Маркета на 00:00 по Москве."},
    )

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    campaign_id = Column(BigInteger, nullable=False, index=True)
    warehouse_id = Column(BigInteger, nullable=False, index=True)
    offer_id = Column(String, nullable=False, index=True)
    stock_type = Column(String, nullable=False, index=True)
    count = Column(Integer, nullable=False, default=0)
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    raw_data = Column(JSON, nullable=False)


class InventorySyncRun(Base):
    __tablename__ = "inventory_sync_runs"
    __table_args__ = {"comment": "Журнал периодических загрузок и ежедневных срезов остатков."}

    id = Column(String, primary_key=True)
    marketplace = Column(String, nullable=False, default="all", index=True)
    run_type = Column(String, nullable=False, index=True)
    snapshot_date = Column(Date, nullable=True, index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, index=True)
    wb_fbs_rows = Column(Integer, nullable=False, default=0)
    wb_fbo_rows = Column(Integer, nullable=False, default=0)
    ozon_rows = Column(Integer, nullable=False, default=0)
    ozon_warehouse_rows = Column(Integer, nullable=False, default=0)
    yandex_market_rows = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)


class OzonSyncRun(Base):
    __tablename__ = "ozon_sync_runs"
    __table_args__ = {"comment": "Журнал независимых заданий синхронизации Ozon."}

    id = Column(String, primary_key=True)
    task = Column(String, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, index=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)


class OzonPosting(Base):
    __tablename__ = "ozon_postings"
    __table_args__ = (
        UniqueConstraint("posting_number", "scheme", name="uq_ozon_posting_number_scheme"),
        {"comment": "Отправления Ozon FBS и FBO."},
    )

    id = Column(Integer, primary_key=True, index=True)
    posting_number = Column(String, nullable=False, index=True)
    order_id = Column(BigInteger, nullable=True, index=True)
    order_number = Column(String, nullable=True, index=True)
    scheme = Column(String(10), nullable=False, index=True)
    status = Column(String, nullable=True, index=True)
    substatus = Column(String, nullable=True, index=True)
    in_process_at = Column(DateTime(timezone=True), nullable=True, index=True)
    shipment_date = Column(DateTime(timezone=True), nullable=True, index=True)
    products = Column(JSON, nullable=False, default=list)
    analytics_data = Column(JSON, nullable=True)
    financial_data = Column(JSON, nullable=True)
    raw_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class OzonSupply(Base):
    __tablename__ = "ozon_supplies"
    id = Column(Integer, primary_key=True)
    supply_order_id = Column(BigInteger, nullable=False, unique=True, index=True)
    supply_order_number = Column(String, nullable=True, index=True)
    state = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    supply_date_from = Column(DateTime(timezone=True), nullable=True)
    supply_date_to = Column(DateTime(timezone=True), nullable=True)
    warehouse_id = Column(BigInteger, nullable=True, index=True)
    warehouse_name = Column(String, nullable=True)
    total_items_count = Column(Integer, nullable=False, default=0)
    total_quantity = Column(Integer, nullable=False, default=0)
    items = Column(JSON, nullable=False, default=list)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonQuestion(Base):
    __tablename__ = "ozon_questions"
    id = Column(Integer, primary_key=True)
    question_id = Column(String, nullable=False, unique=True, index=True)
    sku = Column(BigInteger, nullable=True, index=True)
    text = Column(Text, nullable=False, default="")
    status = Column(String, nullable=True, index=True)
    is_answered = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    answers = Column(JSON, nullable=False, default=list)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonReview(Base):
    __tablename__ = "ozon_reviews"
    id = Column(Integer, primary_key=True)
    review_id = Column(String, nullable=False, unique=True, index=True)
    sku = Column(BigInteger, nullable=True, index=True)
    text = Column(Text, nullable=False, default="")
    rating = Column(Integer, nullable=True, index=True)
    status = Column(String, nullable=True, index=True)
    is_answered = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    comments = Column(JSON, nullable=False, default=list)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonDailySale(Base):
    __tablename__ = "ozon_daily_sales"
    __table_args__ = (UniqueConstraint("sale_date", "sku", name="uq_ozon_daily_sale_date_sku"),)
    id = Column(Integer, primary_key=True)
    sale_date = Column(Date, nullable=False, index=True)
    sku = Column(BigInteger, nullable=False, index=True)
    product_name = Column(String, nullable=True)
    offer_id = Column(String, nullable=True, index=True)
    ordered_units = Column(Integer, nullable=False, default=0)
    delivered_units = Column(Integer, nullable=False, default=0)
    returns = Column(Integer, nullable=False, default=0)
    cancellations = Column(Integer, nullable=False, default=0)
    revenue = Column(Numeric(20, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonFinanceAccrual(Base):
    __tablename__ = "ozon_finance_accruals"
    __table_args__ = (UniqueConstraint("accrual_date", "operation_id", "accrual_type", name="uq_ozon_finance_accrual"),)
    id = Column(Integer, primary_key=True)
    accrual_date = Column(Date, nullable=False, index=True)
    operation_id = Column(String, nullable=False, default="", index=True)
    accrual_type = Column(String, nullable=False, default="unknown", index=True)
    accrual_name = Column(String, nullable=True)
    posting_number = Column(String, nullable=True, index=True)
    amount = Column(Numeric(20, 6), nullable=False, default=0)
    currency = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonAdCampaign(Base):
    __tablename__ = "ozon_ad_campaigns"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(BigInteger, nullable=False, unique=True, index=True)
    title = Column(String, nullable=True)
    state = Column(String, nullable=True, index=True)
    campaign_type = Column(String, nullable=True, index=True)
    payment_type = Column(String, nullable=True)
    budget = Column(Numeric(20, 6), nullable=False, default=0)
    daily_budget = Column(Numeric(20, 6), nullable=False, default=0)
    from_date = Column(Date, nullable=True)
    to_date = Column(Date, nullable=True)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)


class OzonAdDailyStat(Base):
    __tablename__ = "ozon_ad_daily_stats"
    __table_args__ = (UniqueConstraint("stat_date", "campaign_id", "sku", name="uq_ozon_ad_daily_stat"),)
    id = Column(Integer, primary_key=True)
    stat_date = Column(Date, nullable=False, index=True)
    campaign_id = Column(BigInteger, nullable=False, index=True)
    sku = Column(BigInteger, nullable=False, default=0, index=True)
    views = Column(BigInteger, nullable=False, default=0)
    clicks = Column(BigInteger, nullable=False, default=0)
    orders = Column(Integer, nullable=False, default=0)
    orders_money = Column(Numeric(20, 6), nullable=False, default=0)
    spend = Column(Numeric(20, 6), nullable=False, default=0)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
