# wb/orders/notify_order.py
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass
from bot import send_telegram_message
from max.send_message import send_max_groupe


@dataclass
class OrderInfo:
    """Структурированная информация о заказе для уведомления"""
    order_id: int  # ID заказа
    article: str  # Артикул товара
    quantity: int  # Количество (всегда 1 для FBS)
    price: float  # Цена в рублях
    warehouse_id: int  # ID склада отгрузки
    warehouse_name: str = None  # Название склада (если есть)
    office_id: int = None  # ID ПВЗ
    offices: List[str] = None  # Список доступных офисов
    created_at: str = None  # Дата создания заказа
    nm_id: int = None  # Номенклатура WB
    comment: str = None  # Комментарий к заказу

    @property
    def warehouse_display(self) -> str:
        """Форматированное отображение склада"""
        if self.warehouse_name:
            return f"{self.warehouse_name} (ID: {self.warehouse_id})"
        return f"Склад ID: {self.warehouse_id}"

    @property
    def offices_display(self) -> str:
        """Форматированное отображение офисов"""
        if self.offices:
            return ", ".join(self.offices[:3])
        return "Не указан"

    @property
    def price_display(self) -> str:
        """Форматированная цена"""
        return f"{self.price:,.2f}".replace(",", " ")


def parse_order_to_order_info(order: Dict[str, Any]) -> OrderInfo:
    """
    Преобразует данные заказа из API в структурированный объект OrderInfo

    Args:
        order: Словарь с данными заказа из API WB

    Returns:
        OrderInfo: Структурированная информация о заказе
    """
    # Количество товара (в FBS всегда 1 единица на задание)
    quantity = 1

    # Цена в рублях (делим на 100, так как в API приходит в копейках)
    price = order.get('price', 0) / 100

    # Форматируем дату
    created_at = order.get('createdAt', '')
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            created_at = dt.strftime('%d.%m.%Y %H:%M:%S')
        except:
            pass

    return OrderInfo(
        order_id=order.get('id'),
        article=order.get('article', 'Не указан'),
        quantity=quantity,
        price=price,
        warehouse_id=order.get('warehouseId', 0),
        office_id=order.get('officeId'),
        offices=order.get('offices', []),
        created_at=created_at,
        nm_id=order.get('nmId'),
        comment=order.get('comment', '')
    )


def format_new_order_message(order: Dict[str, Any], order_number: int = None) -> str:
    """
    Форматирует сообщение о новом заказе для отправки в Telegram

    Args:
        order: Словарь с данными заказа из API WB
        order_number: Порядковый номер заказа в пакете (опционально)

    Returns:
        str: Отформатированное сообщение для Telegram
    """
    info = parse_order_to_order_info(order)

    # Заголовок
    if order_number:
        header = f"📦 *НОВЫЙ ЗАКАЗ #{order_number}*"
    else:
        header = "📦 *НОВЫЙ ЗАКАЗ WILDBERRIES*"

    # Основная информация
    message = f"{header}\n\n"
    message += f"🆔 **ID заказа:** `{info.order_id}`\n"


    if hasattr(info, 'skus') and info.order_uid and len(info.order_uid) > 0:
        message += f"🔑 **UID заказа:** `{info.order_uid[:30]}...`\n"

    message += f"📅 **Создан:** `{info.created_at or 'Не указано'}`\n\n"

    # Информация о товаре
    message += "━━━━━━━━━━━━━━━━━━━━\n"
    message += "*📦 ТОВАР*\n"
    message += f"📌 **Артикул:** `{info.article}`\n"
    message += f"🔢 **Номенклатура WB:** `{info.nm_id or 'Не указана'}`\n"

    if hasattr(info, 'skus') and info.skus and len(info.skus) > 0:
        sku_str = ", ".join(info.skus[:2])
        if len(info.skus) > 2:
            sku_str += f" и ещё {len(info.skus) - 2}"
        message += f"📊 **SKU:** `{sku_str}`\n"

    message += f"🔢 **Количество:** `{info.quantity} шт.`\n"
    message += f"💰 **Цена:** `{info.price_display} ₽`\n\n"

    # Информация об отгрузке
    message += "━━━━━━━━━━━━━━━━━━━━\n"
    message += "*🚚 ОТГРУЗКА*\n"
    message += f"🏭 **Склад отгрузки:** `{info.warehouse_display}`\n"

    if info.office_id:
        message += f"🏢 **ID ПВЗ:** `{info.office_id}`\n"

    if info.offices:
        message += f"📍 **Доступные офисы:** `{info.offices_display}`\n"

    # Комментарий (если есть)
    if info.comment:
        message += "\n━━━━━━━━━━━━━━━━━━━━\n"
        message += "*💬 КОММЕНТАРИЙ*\n"
        message += f"_{info.comment[:200]}_"

    # Подвал
    message += "\n\n━━━━━━━━━━━━━━━━━━━━\n"
    message += "⚠️ *Требуется сборка и отправка!*"

    return message


def format_multiple_orders_message(orders: List[Dict[str, Any]], max_display: int = 15) -> str:
    """
    Форматирует сообщение о нескольких новых заказах

    Args:
        orders: Список заказов из API
        max_display: Максимальное количество заказов для детального отображения

    Returns:
        str: Отформатированное сообщение для Telegram
    """
    total = len(orders)

    if total == 0:
        return "📭 *Нет новых заказов*"

    if total == 1:
        return format_new_order_message(orders[0])

    # Несколько заказов
    message = f"📦 *НОВЫЕ ЗАКАЗЫ WILDBERRIES*\n\n"
    message += f"Всего получено: `{total}` заказов\n"
    message += f"Отображаем: `{min(total, max_display)}`\n\n"
    message += "━━━━━━━━━━━━━━━━━━━━\n\n"

    # Показываем первые N заказов кратко
    for idx, order in enumerate(orders[:max_display], 1):
        info = parse_order_to_order_info(order)

        message += f"*{idx}. Заказ #{info.order_id}*\n"
        message += f"   📌 Артикул: `{info.article}`\n"
        message += f"   🔢 Кол-во: `{info.quantity} шт.`\n"
        message += f"   💰 Цена: `{info.price_display} ₽`\n"
        message += f"   🏭 Склад: `{info.warehouse_id}`\n\n"

    if total > max_display:
        message += f"*... и ещё {total - max_display} заказов*\n\n"

    message += "━━━━━━━━━━━━━━━━━━━━\n"
    message += "⚠️ *Требуется сборка и отправка всех заказов!*"

    return message


def send_order_notification(orders: List[Dict[str, Any]], chat_id: str) -> Dict[str, Any]:
    """
    Отправляет уведомление о новых заказах в Telegram

    Args:
        orders: Список заказов из API
        chat_id: ID чата Telegram для отправки

    Returns:
        Dict: Статистика отправки
    """
    result = {
        "total_orders": len(orders),
        "sent": 0,
        "failed": 0,
        "errors": []
    }

    if not orders:
        # Нет заказов - отправляем уведомление об отсутствии
        message = "📭 *Нет новых заказов*"
        try:
            send_telegram_message(message, chat_id=chat_id, parse_mode="Markdown")
            result["sent"] = 1
            send_max_groupe(message)
        except Exception as e:
            result["failed"] = 1
            result["errors"].append(str(e))
        return result

    # Если заказов много (больше 3), отправляем сводку
    if len(orders) > 3:
        message = format_multiple_orders_message(orders)
        try:
            send_telegram_message(message, chat_id=chat_id, parse_mode="Markdown")
            result["sent"] = len(orders)

            send_max_groupe(message)

        except Exception as e:
            result["failed"] = len(orders)
            result["errors"].append(str(e))
    else:
        # Мало заказов - отправляем каждый отдельно
        for idx, order in enumerate(orders, 1):
            try:
                message = format_new_order_message(order, order_number=idx)
                send_telegram_message(message, chat_id=chat_id, parse_mode="Markdown")
                send_max_groupe(message)
                result["sent"] += 1
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"Order {order.get('id')}: {str(e)}")

    return result


# ===== Пример использования =====
def notify_new_orders(orders: List[Dict[str, Any]], chat_id: str):
    """
    Упрощенная функция для уведомления о новых заказах

    Args:
        orders: Список заказов
        chat_id: ID чата Telegram
    """
    if not orders:
        return

    result = send_order_notification(orders, chat_id)


    if result["failed"] > 0:
        print(f"⚠️ Не удалось отправить {result['failed']} уведомлений")
        for error in result["errors"]:
            print(f"   Ошибка: {error}")
        return None
    else:
        print(f"✅ Отправлено {result['sent']} уведомлений о заказах")
        return True


