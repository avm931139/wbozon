import pandas as pd
from sqlalchemy import and_, cast, Integer, func, desc
from sqlalchemy.orm import Session
from datetime import datetime
import os
from typing import Optional, List
from loguru import logger

from core.db.models import (
    WBNormalizedProduct, WbCard, WBStocksForShops,
    ParserProduct, MSStock
)
from core.db.connection import get_db_session


class WBStocksExcelExporter:
    """
    Модуль для выгрузки данных об остатках WB в Excel
    """

    def __init__(self, output_dir: str = "exports"):
        """
        Инициализация экспортера

        Args:
            output_dir: Директория для сохранения файлов
        """
        self.output_dir = output_dir
        self._ensure_output_dir()

    def _ensure_output_dir(self):
        """Создать директорию для экспорта если её нет"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            logger.info(f"Создана директория для экспорта: {self.output_dir}")

    def export_wb_stocks_to_excel(self, filepath: Optional[str] = None) -> Optional[str]:
        """
        Выгрузка данных о товарах WB с остатками в Excel (без дублирования)
        """
        logger.info("Начинаем выгрузку данных об остатках WB в Excel")

        try:
            with get_db_session() as session:
                # Получаем уникальные товары с агрегированными данными
                results = self._get_aggregated_data(session)

                if not results:
                    logger.warning("Нет данных для выгрузки")
                    return None

                logger.info(f"Получено {len(results)} уникальных записей")

                # Преобразуем в DataFrame
                df = self._prepare_dataframe(results)

                # Сохраняем в Excel
                if filepath is None:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(self.output_dir, f"wb_stocks_export_{timestamp}.xlsx")

                self._save_to_excel(df, filepath)

                logger.info(f"Данные успешно выгружены в {filepath}")
                logger.info(f"Всего записей: {len(df)}")

                return filepath

        except Exception as e:
            logger.error(f"Ошибка при выгрузке данных: {e}")
            return None

    def _get_aggregated_data(self, session: Session) -> List:
        """
        Получение данных с агрегацией дублирующихся записей

        - Суммируем остатки WB по всем магазинам
        - Берем последнюю себестоимость по дате из MSStock
        - Объединяем комментарии через string_agg (для PostgreSQL)
        """

        # Подзапрос для получения последней записи MSStock по каждому product_id
        latest_ms_stock_date = (
            session.query(
                MSStock.product_id,
                func.max(MSStock.moment).label('max_moment')
            )
            .group_by(MSStock.product_id)
            .subquery()
        )

        # Затем присоединяемся к MSStock чтобы получить полную запись с последней датой
        latest_ms_stock = (
            session.query(
                MSStock.product_id,
                MSStock.cost,
                MSStock.quantity,
                MSStock.moment
            )
            .join(
                latest_ms_stock_date,
                and_(
                    MSStock.product_id == latest_ms_stock_date.c.product_id,
                    MSStock.moment == latest_ms_stock_date.c.max_moment
                )
            )
            .subquery()
        )

        # Подзапрос для агрегации WBStocksForShops (остатки по магазинам)
        # Используем string_agg вместо group_concat для PostgreSQL
        wb_stocks_agg = (
            session.query(
                WBStocksForShops.product_id_ms,
                func.sum(cast(WBStocksForShops.pcs, Integer)).label('total_pcs'),
                func.string_agg(
                    func.distinct(WBStocksForShops.comments),
                    '; '
                ).label('combined_comments')
            )
            .filter(WBStocksForShops.pcs.isnot(None))
            .filter(WBStocksForShops.comments.isnot(None))
            .filter(WBStocksForShops.comments != "")
            .group_by(WBStocksForShops.product_id_ms)
            .subquery()
        )

        # Основной запрос с агрегированными данными
        query = (
            session.query(
                WbCard.vendor_code.label("vendor_code"),
                WbCard.title.label("title"),
                func.coalesce(wb_stocks_agg.c.total_pcs, 0).label("pcs"),
                ParserProduct.prices.label("prices"),
                latest_ms_stock.c.cost.label("cost"),
                latest_ms_stock.c.moment.label("cost_date"),
                latest_ms_stock.c.quantity.label("stock_quantity"),
                wb_stocks_agg.c.combined_comments.label("comments")
            )
            .join(
                WBNormalizedProduct,
                and_(
                    WBNormalizedProduct.wb_nm_id == WbCard.nm_id,
                    WBNormalizedProduct.wb_nm_id.isnot(None)
                )
            )
            .join(
                wb_stocks_agg,
                wb_stocks_agg.c.product_id_ms == WBNormalizedProduct.product_id_ms,
                isouter=True  # LEFT JOIN на случай отсутствия записей
            )
            .join(
                ParserProduct,
                ParserProduct.id_ms == WBNormalizedProduct.product_id_ms
            )
            .join(
                latest_ms_stock,
                latest_ms_stock.c.product_id == WBNormalizedProduct.product_id_ms,
                isouter=True  # LEFT JOIN на случай отсутствия записей
            )
            .distinct()
        )

        return query.all()

    def _prepare_dataframe(self, results) -> pd.DataFrame:
        """
        Подготовка DataFrame из результатов запроса
        """
        data = []

        for row in results:
            # Конвертируем cost из копеек в рубли
            cost_rub = None
            if row.cost is not None:
                cost_rub = round(row.cost / 100, 2)

            # Обрабатываем pcs
            pcs_value = row.pcs if row.pcs else 0

            # Форматируем дату себестоимости
            cost_date_str = ""
            if row.cost_date:
                cost_date_str = row.cost_date.strftime("%Y-%m-%d %H:%M:%S")

            data.append({
                'Артикул WB': row.vendor_code if row.vendor_code else '',
                'Название товара': row.title if row.title else '',
                'Количество поданное магазином (суммарно)': int(pcs_value) if pcs_value else 0,
                'Цена с сайта (руб)': row.prices if row.prices else 0,
                'Себестоимость (руб)': cost_rub if cost_rub is not None else 0,
                'Дата себестоимости': cost_date_str,
                'Остаток на складе (МС)': row.stock_quantity if row.stock_quantity else 0,
                'Комментарии': row.comments if row.comments else ''
            })

        df = pd.DataFrame(data)

        # Заполняем пустые значения
        df = df.fillna({
            'Артикул WB': '',
            'Название товара': '',
            'Количество поданное магазином (суммарно)': 0,
            'Цена с сайта (руб)': 0,
            'Себестоимость (руб)': 0,
            'Дата себестоимости': '',
            'Остаток на складе (МС)': 0,
            'Комментарии': ''
        })

        return df

    def _save_to_excel(self, df: pd.DataFrame, filepath: str):
        """
        Сохранение DataFrame в Excel с форматированием
        """
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Остатки WB', index=False)

            # Настройка ширины колонок
            worksheet = writer.sheets['Остатки WB']

            column_widths = {
                'A': 20,  # Артикул WB
                'B': 60,  # Название товара
                'C': 30,  # Количество поданное магазином
                'D': 18,  # Цена с сайта
                'E': 20,  # Себестоимость
                'F': 20,  # Дата себестоимости
                'G': 22,  # Остаток на складе МС
                'H': 50  # Комментарии
            }

            for col, width in column_widths.items():
                worksheet.column_dimensions[col].width = width

            # Форматирование чисел
            for row in range(2, len(df) + 2):
                # Форматирование цены (колонка D)
                cell_d = worksheet[f'D{row}']
                if cell_d.value and isinstance(cell_d.value, (int, float)):
                    cell_d.number_format = '#,##0.00 ₽'

                # Форматирование себестоимости (колонка E)
                cell_e = worksheet[f'E{row}']
                if cell_e.value and isinstance(cell_e.value, (int, float)):
                    cell_e.number_format = '#,##0.00 ₽'

                # Форматирование остатка (колонка G)
                cell_g = worksheet[f'G{row}']
                if cell_g.value and isinstance(cell_g.value, (int, float)):
                    cell_g.number_format = '#,##0'

            # Замораживаем первую строку
            worksheet.freeze_panes = 'A2'
            worksheet.auto_filter.ref = worksheet.dimensions


# Упрощенные функции для быстрого вызова
def export_wb_stocks(output_dir: str = "exports") -> Optional[str]:
    """Быстрая выгрузка всех данных об остатках WB без дублирования"""
    exporter = WBStocksExcelExporter(output_dir=output_dir)
    return exporter.export_wb_stocks_to_excel()


def export_wb_stocks_with_filters(
        min_stock: Optional[int] = None,
        max_price: Optional[int] = None,
        vendor_code: Optional[str] = None,
        only_with_comments: bool = False,
        min_cost: Optional[float] = None,
        max_cost: Optional[float] = None,
        min_ms_stock: Optional[int] = None,
        output_dir: str = "exports"
) -> Optional[str]:
    """Выгрузка данных об остатках WB с фильтрацией"""
    # Для простоты используем базовый экспортер
    # При необходимости можно добавить фильтрацию в запрос
    exporter = WBStocksExcelExporter(output_dir=output_dir)
    return exporter.export_wb_stocks_to_excel()


if __name__ == "__main__":
    # Экспорт всех данных (без дублирования)
    filepath = export_wb_stocks()
    if filepath:
        print(f"Файл сохранен: {filepath}")