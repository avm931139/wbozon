# utils.py
from datetime import datetime
from typing import Dict, Any, Optional
from core.db.connection import get_db_session
from core.db.models import WbFbsOrder


def parse_wb_order_to_model(order_data: Dict[str, Any]) -> WbFbsOrder:
    """
    Преобразует данные заказа из API Wildberries в объект модели SQLAlchemy

    Args:
        order_data: Словарь с данными заказа из API WB

    Returns:
        WbFbsOrder: Объект модели для сохранения в БД
    """
    # Парсим дату создания
    created_at = None
    if order_data.get('createdAt'):
        created_at = datetime.fromisoformat(order_data['createdAt'].replace('Z', '+00:00'))

    order = WbFbsOrder(
        # Основные поля
        id=order_data.get('id'),
        order_uid=order_data.get('orderUid', ''),
        rid=order_data.get('rid'),

        # Информация о товаре
        article=order_data.get('article'),
        nm_id=order_data.get('nmId'),
        chrt_id=order_data.get('chrtId'),
        skus=order_data.get('skus'),

        # Цены
        price=order_data.get('price'),
        final_price=order_data.get('finalPrice'),
        sale_price=order_data.get('salePrice'),
        converted_price=order_data.get('convertedPrice'),
        converted_final_price=order_data.get('convertedFinalPrice'),

        # Валюты
        currency_code=order_data.get('currencyCode'),
        converted_currency_code=order_data.get('convertedCurrencyCode'),

        # Доставка
        delivery_type=order_data.get('deliveryType'),
        cargo_type=order_data.get('cargoType'),
        cross_border_type=order_data.get('crossBorderType'),

        # Склады и офисы
        warehouse_id=order_data.get('warehouseId'),
        office_id=order_data.get('officeId'),
        offices=order_data.get('offices'),

        # Метаданные маркировки
        required_meta=order_data.get('requiredMeta'),
        optional_meta=order_data.get('optionalMeta'),

        # Дополнительно
        address=order_data.get('address'),
        comment=order_data.get('comment'),
        scan_price=order_data.get('scanPrice'),
        color_code=order_data.get('colorCode'),
        is_zero_order=order_data.get('isZeroOrder', False),
        options=order_data.get('options'),
        user_id=order_data.get('userId'),

        # Системные поля
        created_at_wb=created_at,

        # Telegram флаг (по умолчанию False)
        send_mes_tg=False,
    )

    return order


def save_orders_to_db(orders_data: list) -> int:
    """
    Сохраняет список заказов в БД с обработкой конфликтов

    Args:
        session: Сессия SQLAlchemy
        orders_data: Список словарей с данными заказов из API

    Returns:
        int: Количество успешно сохраненных заказов
    """
    saved_count = 0
    try:
        with get_db_session() as session:
            for order_dict in orders_data:
                # Проверяем, существует ли уже заказ с таким id
                existing_order = session.query(WbFbsOrder).filter_by(id=order_dict.get('id')).first()

                if not existing_order:
                    # Создаем новый заказ
                    order = parse_wb_order_to_model(order_dict)
                    session.add(order)
                    saved_count += 1

            # Сохраняем все изменения
            session.commit()

            return saved_count
    except Exception as e:
        return e


def get_unsent_orders(limit: int = 100):
    """
    Получает заказы, которые еще не были отправлены в Telegram

    Args:
        session: Сессия SQLAlchemy
        limit: Максимальное количество заказов

    Returns:
        list: Список заказов, ожидающих отправки
    """
    with get_db_session() as session:
        return session.query(WbFbsOrder).filter_by(send_mes_tg=False).limit(limit).all()


def mark_order_as_sent(orders: list):
    """
    Отмечает заказ как отправленный в Telegram

    Args:
        session: Сессия SQLAlchemy
        order_id: ID заказа
    """
    with get_db_session() as session:
        # for order in orders:
        #     order = session.query(WbFbsOrder).filter(WbFbsOrder.id==order.id).first()
        #     if order:
        #         order.send_mes_tg = True
        #         order.sent_to_tg_at = datetime.utcnow()
        #         session.commit()
        pass


def get_for_send_orders():
    """
    Получает все не отправленные заказы из БД

    Returns:
        list: Список словарей с основными данными заказов
    """
    with get_db_session() as session:
        # Получаем не отправленные заказы
        orders = session.query(WbFbsOrder).filter(
            (WbFbsOrder.send_mes_tg == False) | (WbFbsOrder.send_mes_tg == None)
        ).all()

        # Формируем список словарей только с нужными полями
        orders_list = []
        for order in orders:
            order_dict = {
                'id': order.id,
                'order_uid': order.order_uid,
                'article': order.article,
                'nm_id': order.nm_id,
                'skus': order.skus,
                'price': order.price / 100 if order.price else 0,  # переводим в рубли
                'warehouse_id': order.warehouse_id,
                'office_id': order.office_id,
                'offices': order.offices,
                'comment': order.comment,
                'created_at': order.created_at_wb.strftime('%d.%m.%Y %H:%M:%S') if order.created_at_wb else None,
                'send_mes_tg': order.send_mes_tg,
            }
            orders_list.append(order_dict)

        return orders_list
