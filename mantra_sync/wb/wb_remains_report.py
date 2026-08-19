# matra_sync/tools/wb_remains_report.py
import requests
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from core.classes import Wb
from settings import Config
from bot import send_telegram_message
from core.db.connection import get_db_session
from core.db.models import WbRemainsReport, WbRemainsReportData, WbStock
from wb import endpoind_wb
from core.classes import Wb


class WBRemainsReport(Wb):
    """
    Класс для работы с отчетами об остатках на складах WB
    Документация: https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains
    """

    def __init__(self, account=None):
        if account:
            self.account = account
        else:
            self.account = None

        super().__init__()

        self.base_url = endpoind_wb.base_url_seller_analytics
        self.report_endpoint = endpoind_wb.warehouse_remains
        self.status_endpoint = endpoind_wb.status
        self.download_endpoint = endpoind_wb.download_report

    def create_report(self, params: Dict[str, Any] = None) -> Optional[str]:
        """
        Создает задание на генерацию отчета об остатках
        """
        headers = self.get_headers()
        if not headers:
            print("❌ Нет заголовков авторизации")
            return None

        # Параметры по умолчанию
        default_params = {
            "locale": "ru",
            "groupByBrand": False,
            "groupBySubject": False,
            "groupBySa": True,
            "groupByNm": True,
            "groupByBarcode": True,
            "groupBySize": False,
            "filterPics": 0,
            "filterVolume": 0
        }

        if params:
            default_params.update(params)

        url = urljoin(self.base_url, self.report_endpoint)

        try:
            print(f"📊 Создание отчета об остатках с параметрами: {default_params}")
            response = requests.get(url, headers=headers, params=default_params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                task_id = data['data'].get('taskId')
                if task_id:
                    print(f"✅ Задача создана, ID: {task_id}")
                    self._save_report_task(task_id, default_params)
                    return task_id
                else:
                    print(f"❌ Нет taskId в ответе: {data}")
                    return None
            elif response.status_code == 401:
                print("❌ Ошибка авторизации. Проверьте API ключ")
                return None
            elif response.status_code == 429:
                print("⚠️ Превышен лимит запросов. Ожидание 60 секунд...")
                time.sleep(60)
                return self.create_report(params)
            else:
                print(f"❌ Ошибка создания отчета: {response.status_code}")
                print(f"Ответ: {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка запроса: {e}")
            return None

    def check_report_status(self, task_id: str) -> Dict[str, Any]:
        """
        Проверяет статус выполнения отчета
        """
        headers = self.get_headers()
        url = urljoin(self.base_url, f"{self.status_endpoint}/{task_id}/status")

        try:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                status = data['data'].get('status')
                print(f"📊 Статус отчета {task_id}: {status}")


                return data
            else:
                print(f"❌ Ошибка проверки статуса: {response.status_code}")
                return {'status': 'error', 'error': response.text}

        except Exception as e:
            print(f"❌ Ошибка при проверке статуса: {e}")
            return {'status': 'error', 'error': str(e)}


    def download_report(self, task_id: str) -> Optional[List[Dict]]:
        """
        Скачивает готовый отчет
        """
        headers = self.get_headers()
        url = urljoin(self.base_url, f"{self.download_endpoint}/{task_id}/download")

        try:
            print(f"📥 Скачивание отчета {task_id}...")
            response = requests.get(url, headers=headers, timeout=60)

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Отчет получен, записей: {len(data)}")

                # Сохраняем данные отчета
                self._save_fbo_stocks_from_report(data)

                return data
            elif response.status_code == 404:
                print(f"❌ Отчет не найден или еще не готов")
                return None
            else:
                print(f"❌ Ошибка скачивания: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Ошибка при скачивании: {e}")
            return None

    def _save_fbo_stocks_from_report(self, report_data: List[Dict]):
        """
        Сохраняет данные отчета FBO в таблицу WbStock
        - Если запись за сегодня уже существует - обновляет
        - Если записи нет - создает новую
        """
        try:
            with get_db_session() as db:
                from sqlalchemy import and_, func

                today = datetime.now().date()
                created_count = 0
                updated_count = 0
                saved = 0

                for item in report_data:
                    # Получаем данные из отчета
                    nm_id = item.get('nmId')
                    if not nm_id:
                        continue

                    warehouse_id = item.get('warehouseId', 0)
                    vendor_code = item.get('vendorCode', '')

                    warehouses = item.get('warehouses', 0)

                    quantity = 0

                    if warehouses !=0:
                        for warehouse in warehouses:
                            warehouse_name = warehouse.get('warehouseName', 0)
                            if warehouse_name == 'Всего находится на складах':
                                quantity = warehouse.get('quantity', 0)


                    # Ищем существующую запись за сегодня
                    existing = db.query(WbStock).filter(
                        and_(
                            WbStock.nm_id_wb == nm_id,
                            WbStock.type_wharehouse == 'fbo',
                            WbStock.wharehouse_seller_wb == warehouse_id,
                            func.date(WbStock.updated_at) == today
                        )
                    ).first()

                    if existing:
                        # Обновляем существующую запись
                        existing.pcs = quantity
                        existing.artikul_wb = vendor_code
                        existing.updated_at = datetime.now()
                        updated_count += 1
                    else:
                        # Создаем новую запись
                        new_stock = WbStock(
                            product_id=str(nm_id),
                            type_wharehouse='fbo',
                            artikul_wb=vendor_code,
                            nm_id_wb=nm_id,
                            pcs=quantity,
                            wharehouse_seller_wb=warehouse_id,
                            id_ul=Config.DEFAULT_UL_ID,
                            updated_at=datetime.now()
                        )
                        db.add(new_stock)
                        created_count += 1

                    saved += 1

                    # Периодический flush для оптимизации
                    if saved % 500 == 0:
                        db.flush()
                        print(f"💾 Промежуточно: создано {created_count}, обновлено {updated_count}")

                db.commit()
                print(f"✅ Остатки FBO: создано {created_count}, обновлено {updated_count}, всего {saved} записей")
                return saved

        except Exception as e:
            print(f"❌ Ошибка сохранения FBO остатков: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return 0
    def wait_for_report(self, task_id: str, max_wait: int = 300, check_interval: int = 10) -> Optional[List[Dict]]:
        """
        Ожидает готовности отчета и скачивает его
        """
        start_time = time.time()
        elapsed = 0

        print(f"⏳ Ожидание готовности отчета {task_id}...")

        while elapsed < max_wait:
            status_data = self.check_report_status(task_id)
            status = status_data.get('data', {}).get('status') if isinstance(status_data, dict) else None

            if status == 'done':
                print("✅ Отчет готов, скачиваем...")
                return self.download_report(task_id)
            elif status == 'error':
                print(f"❌ Ошибка при генерации отчета: {status_data}")
                return None
            elif status == 'processing':
                print(f"⏳ Отчет в обработке... ({elapsed:.0f}/{max_wait} сек)")
            else:
                print(f"ℹ️ Статус: {status}")

            time.sleep(check_interval)
            elapsed = time.time() - start_time

        print(f"❌ Таймаут ожидания отчета ({max_wait} сек)")
        return None

    def generate_remains_report(self, params: Dict[str, Any] = None, wait: bool = True) -> Optional[List[Dict]]:
        """
        Полный цикл: создание, ожидание и получение отчета
        """
        task_id = self.create_report(params)

        if not task_id:
            return None

        if wait:
            return self.wait_for_report(task_id)
        else:
            print(f"📝 Задача создана, ID: {task_id}")
            return None

    def _save_report_task(self, task_id: str, params: Dict[str, Any]):
        """Сохраняет информацию о задаче в БД"""
        try:
            with get_db_session() as db:
                report = WbRemainsReport(
                    task_id=task_id,
                    params=params,
                    status='created',
                    created_at=datetime.now(),
                    id_ul=self.account.get('ul_id', Config.DEFAULT_UL_ID) if self.account else Config.DEFAULT_UL_ID
                )
                db.add(report)
                db.commit()
                print(f"💾 Задача {task_id} сохранена в БД")
        except Exception as e:
            print(f"❌ Ошибка сохранения задачи в БД: {e}")


# Функция для использования в планировщике
def get_wb_remains_report_job():
    """
    Ежедневная задача: создание и получение отчета об остатках
    """
    print("=" * 60)
    print("🚀 НАЧАЛО ЗАГРУЗКИ ОТЧЕТА ОБ ОСТАТКАХ WB")
    print("=" * 60)

    # Параметры отчета
    params = {
        "groupByBrand": True,
        "groupBySubject": True,
        "groupBySa": True,
        "groupByNm": True,
        "groupByBarcode": True,
        "groupBySize": False,
        "filterPics": 0,
        "filterVolume": 0,
        "locale": "ru"
    }

    reporter = WBRemainsReport()

    # Создаем отчет и ждем его готовности
    result = reporter.generate_remains_report(params, wait=True)

    if result:
        records_count = len(result)
        print(f"\n✅ Отчет успешно получен, записей: {records_count}")

        # Отправляем уведомление в Telegram
        message = (
            f"📊 *Отчет об остатках FBO WB*\n"
            f"✅ Успешно загружен\n"
            f"📦 Записей: {records_count}\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        send_telegram_message(message, parse_mode="Markdown")

        return records_count
    else:
        print("❌ Не удалось получить отчет")
        send_telegram_message("❌ Ошибка получения отчета об остатках WB")
        return 0


# Для тестирования (раскомментируйте при необходимости)
if __name__ == "__main__":
    get_wb_remains_report_job()