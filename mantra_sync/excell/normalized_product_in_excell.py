import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from typing import Dict, List
from loguru import logger
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import os

from core.db.models import WBNormalizedProduct, WBNormalizedProductImage, WBNormalizedCharacteristic
from core.db.connection import get_db_session


class ProductExporter:
    """
    Класс для выгрузки данных о товарах в Excel файлы
    """

    def __init__(self, output_dir: str = "exports"):
        self.output_dir = output_dir
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        """Создать директорию для экспорта если её нет"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def _get_characteristics_dict(self, characteristics: List[WBNormalizedCharacteristic]) -> Dict[str, str]:
        """
        Преобразовать список характеристик в словарь

        Ключ: charc_name (или charc_id если нет имени)
        Значение: value
        """
        chars_dict = {}
        for char in characteristics:
            # Используем название характеристики, если есть, иначе ID
            key = char.charc_name if char.charc_name else f"char_{char.charc_id}"
            chars_dict[key] = char.value
        return chars_dict

    def export_all_products(self):
        """
        Экспортировать все товары, сгруппированные по subject_id
        """
        logger.info("Начинаем экспорт товаров в Excel")

        with get_db_session() as session:
            # Получаем все товары с их характеристиками и изображениями
            products = session.query(WBNormalizedProduct).options(
                joinedload(WBNormalizedProduct.characteristics),
                joinedload(WBNormalizedProduct.sizes)
            ).all()

            if not products:
                logger.warning("Нет товаров для экспорта")
                return

            # Группируем товары по subject_id
            products_by_subject: Dict[int, List[WBNormalizedProduct]] = {}
            for product in products:
                subject_id = product.subject_id
                if subject_id not in products_by_subject:
                    products_by_subject[subject_id] = []
                products_by_subject[subject_id].append(product)

            # Экспортируем каждую группу в отдельный файл
            for subject_id, subject_products in products_by_subject.items():
                self._export_products_to_excel(session, subject_id, subject_products)

            logger.info(f"Экспорт завершен. Создано файлов: {len(products_by_subject)}")

    def _export_products_to_excel(self, session: Session, subject_id: int, products: List[WBNormalizedProduct]):
        """
        Экспортировать товары одной категории в Excel файл
        """
        # Получаем название категории из первого товара
        subject_name = products[0].subject_name if products[0].subject_name else f"subject_{subject_id}"
        # Очищаем имя файла от недопустимых символов
        safe_name = "".join(c for c in subject_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{self.output_dir}/{safe_name}_{subject_id}.xlsx"

        logger.info(f"Экспортируем {len(products)} товаров в {filename}")

        # Собираем все возможные названия характеристик для этой категории
        all_char_names = set()
        for product in products:
            for char in product.characteristics:
                char_name = char.charc_name if char.charc_name else f"char_{char.charc_id}"
                all_char_names.add(char_name)

        # Сортируем названия характеристик
        all_char_names = sorted(all_char_names)

        # Формируем данные для DataFrame
        rows_data = []

        for product in products:
            # Получаем изображения для товара
            images = session.query(WBNormalizedProductImage).filter(
                WBNormalizedProductImage.product_id_ms == product.product_id_ms
            ).first()

            # Базовые поля
            row = {
                'product_id_ms': product.product_id_ms,
                'subject_name': product.subject_name,
                'wb_title': product.wb_title,
                'wb_brand': product.wb_brand,
                'length_cm': product.length,
                'width_cm': product.width,
                'height_cm': product.height,
                'weight_kg': product.weight,
                'images_url': images.url if images else '',
                'images_count': images.position if images else 0,
                'status': product.status,
                'wb_nm_id': product.wb_nm_id if product.wb_nm_id else '',
                'vendor_code': product.vendor_code
            }

            # Добавляем характеристики
            chars_dict = self._get_characteristics_dict(product.characteristics)
            for char_name in all_char_names:
                row[char_name] = chars_dict.get(char_name, '')

            rows_data.append(row)

        # Создаем DataFrame
        df = pd.DataFrame(rows_data)

        # Заполняем NaN пустыми строками
        df = df.fillna('')

        # Создаем Excel файл с форматированием
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Товары', index=False)

            # Форматируем Excel
            worksheet = writer.sheets['Товары']

            # Настройка стилей
            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            # Применяем стили к заголовкам
            for col in worksheet.columns:
                max_length = 0
                column_letter = col[0].column_letter

                for cell in col:
                    if cell.row == 1:  # Заголовок
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = header_alignment
                    else:
                        # Выравнивание для данных
                        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

                    # Вычисляем максимальную длину для автоширины
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = min(len(str(cell.value)), 50)  # Ограничиваем 50 символами
                    except:
                        pass

                # Устанавливаем ширину колонки
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

            # Замораживаем первую строку
            worksheet.freeze_panes = 'A2'

        logger.info(f"Файл сохранен: {filename}")

    def export_filtered_products(self, subject_id: int = None, status: str = None):
        """
        Экспортировать товары с фильтрацией

        :param subject_id: ID категории (опционально)
        :param status: статус товара (опционально)
        """
        logger.info(f"Экспорт с фильтром: subject_id={subject_id}, status={status}")

        with get_db_session() as session:
            query = session.query(WBNormalizedProduct).options(
                joinedload(WBNormalizedProduct.characteristics)
            )

            if subject_id:
                query = query.filter(WBNormalizedProduct.subject_id == subject_id)

            if status:
                query = query.filter(WBNormalizedProduct.status == status)

            products = query.all()

            if not products:
                logger.warning("Нет товаров по заданным фильтрам")
                return

            # Определяем имя файла
            filename_parts = []
            if subject_id:
                filename_parts.append(f"subject_{subject_id}")
            if status:
                filename_parts.append(status)
            filename = f"{self.output_dir}/export_{'_'.join(filename_parts)}.xlsx"

            self._export_products_list_to_excel(session, products, filename)

    def _export_products_list_to_excel(self, session: Session, products: List[WBNormalizedProduct], filename: str):
        """
        Экспортировать список товаров в Excel
        """
        # Собираем характеристики
        all_char_names = set()
        for product in products:
            for char in product.characteristics:
                char_name = char.charc_name if char.charc_name else f"char_{char.charc_id}"
                all_char_names.add(char_name)

        all_char_names = sorted(all_char_names)

        # Формируем данные
        rows_data = []

        for product in products:
            images = session.query(WBNormalizedProductImage).filter(
                WBNormalizedProductImage.product_id_ms == product.product_id_ms
            ).first()

            row = {
                'product_id_ms': product.product_id_ms,
                'subject_id': product.subject_id,
                'subject_name': product.subject_name,
                'vendor_code': product.vendor_code,
                'wb_title': product.wb_title,
                'wb_brand': product.wb_brand,
                'length_cm': product.length,
                'width_cm': product.width,
                'height_cm': product.height,
                'weight_kg': product.weight,
                'images_url': images.url if images else '',
                'images_count': images.position if images else 0,
                'status': product.status,
                'wb_nm_id': product.wb_nm_id if product.wb_nm_id else '',
                'validation_errors': product.validation_errors
            }

            chars_dict = self._get_characteristics_dict(product.characteristics)
            for char_name in all_char_names:
                row[char_name] = chars_dict.get(char_name, '')

            rows_data.append(row)

        df = pd.DataFrame(rows_data)
        df = df.fillna('')

        df.to_excel(filename, sheet_name='Товары', index=False)
        logger.info(f"Экспортировано {len(products)} товаров в {filename}")


# Функция для быстрого запуска
def export_all_products():
    """Экспортировать все товары"""
    exporter = ProductExporter()
    exporter.export_all_products()


def export_by_subject_id(subject_id: int):
    """Экспортировать товары по ID категории"""
    exporter = ProductExporter()
    exporter.export_filtered_products(subject_id=subject_id)


def export_by_status(status: str):
    """Экспортировать товары по статусу"""
    exporter = ProductExporter()
    exporter.export_filtered_products(status=status)


if __name__ == "__main__":
    # Экспорт всех товаров
    export_all_products()

    # Или экспорт по категории
    # export_by_subject_id(123)

    # Или экспорт по статусу
    # export_by_status('review')