# matra_sync/tools/wb_stocks_fbo.py
from datetime import datetime
from sqlalchemy.orm import Session
from core.db.connection import get_db_session
from core.db.models import WbStock
from bot import send_telegram_message
from core.classes import Wb
from wb.endpoind_wb import base_url_mp_wb, get_stocks_fbo
from urllib.parse import urljoin
from settings import Config


def notify(step: str, success: bool = True, error: Exception = None):
    """Отправка сообщения в Telegram и логирование в консоль."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if success:
        message = f"✅ [FBO] [{timestamp}] {step} успешно выполнен"
    else:
        message = f"❌ [FBO] [{timestamp}] {step} завершился с ошибкой: {error}"
    print(message)
    try:
        send_telegram_message(message)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


def get_wb_stocks_fbo():
    """
    Загружает остатки FBO (товары на складах Wildberries)
    """
    wb = Wb()
    print("=" * 60)
    print("🚀 НАЧАЛО ЗАГРУЗКИ ОСТАТКОВ FBO")
    print("=" * 60)

    with get_db_session() as db:
        # Очищаем старые остатки FBO
        deleted = db.query(WbStock).filter(WbStock.type_wharehouse == 'fbo').delete()
        print(f"🗑️ Удалено старых остатков FBO: {deleted}")
        db.commit()

        # Формируем URL для запроса остатков FBO
        url = urljoin(base_url_mp_wb, get_stocks_fbo)
        print(f"📡 URL запроса: {url}")

        try:
            # Получаем данные от API WB
            # Предполагается, что у вас есть метод get_fbo_stocks в классе Wb
            data_list = wb.get_fbo_stocks(url)

            if not data_list:
                notify("Нет данных об остатках FBO", False)
                return 0

            print(f"📦 Получено записей от API: {len(data_list)}")

            saved_count = 0
            errors_count = 0

            for data in data_list:
                try:
                    # Извлекаем данные из ответа API
                    # Формат ответа может отличаться, нужно уточнить
                    sku = data.get('sku') or data.get('barcode')
                    nm_id = data.get('nmId') or data.get('nm_id')
                    amount = data.get('amount') or data.get('quantity') or data.get('stock', 0)

                    if not nm_id:
                        print(f"⚠️ Пропуск записи без nm_id: {data}")
                        errors_count += 1
                        continue

                    # Получаем информацию о товаре из БД
                    card_data = wb.get_card_wb(sku or nm_id)

                    if not card_data:
                        print(f"⚠️ Не найдена карточка для nm_id: {nm_id}")
                        errors_count += 1
                        continue

                    # Сохраняем остаток
                    save_fbo_stock(db, data, card_data, amount)
                    saved_count += 1

                    if saved_count % 100 == 0:
                        print(f"💾 Сохранено {saved_count} записей...")
                        db.flush()

                except Exception as e:
                    print(f"❌ Ошибка при обработке записи: {e}")
                    errors_count += 1
                    continue

            db.commit()

            result_message = (
                f"✅ Загрузка FBO завершена:\n"
                f"   • Сохранено: {saved_count}\n"
                f"   • Ошибок: {errors_count}"
            )
            notify(result_message, True)
            print("=" * 60)

            return saved_count

        except Exception as e:
            notify(f"Ошибка при загрузке остатков FBO: {e}", False)
            print(f"❌ Детали ошибки: {e}")
            import traceback
            traceback.print_exc()
            return 0


def save_fbo_stock(db: Session, api_data: dict, card_data: dict, pcs: int):
    """
    Сохраняет запись об остатке FBO
    """
    # Получаем ID склада (для FBO это может быть специальное значение)
    warehouse_id = api_data.get('warehouseId') or api_data.get('warehouse_id', 0)

    new_rec = WbStock(
        product_id=str(api_data.get('nmId', card_data.get('nm_id'))),
        type_wharehouse='fbo',
        artikul_wb=card_data.get('vendor_code', ''),
        nm_id_wb=card_data.get('nm_id'),
        pcs=pcs,
        wharehouse_seller_wb=warehouse_id,
        id_ul=Config.DEFAULT_UL_ID,
        updated_at=datetime.now()
    )
    db.add(new_rec)


def get_fbo_warehouses() -> list:
    """
    Получает список складов FBO
    """
    # Для FBO обычно есть специальный список складов
    # Можно либо получить из API, либо использовать предопределенный список
    return [1]  # Пример: склад FBO с ID 1