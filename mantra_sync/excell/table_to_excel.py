import os
import re
from sqlalchemy import inspect
from openpyxl import Workbook
from core.db.connection import get_db_session  # Импортируем класс для работы с сессией
from sqlalchemy.ext.declarative import DeclarativeMeta
from core.db.models import *

def export_table_to_excel(model_class: DeclarativeMeta, output_dir: str = 'Report'):
    with get_db_session() as db:
        mapper = inspect(model_class)
        data = [
            {col.name: getattr(row, col.name) for col in mapper.columns}
            for row in db.query(model_class).all()
        ]  # здесь всё загружено пока сессия открыта

    wb = Workbook()
    ws = wb.active
    ws.title = model_class.__tablename__

    headers = [col.comment if col.comment else col.name for col in mapper.columns]
    ws.append(headers)

    for row in data:
        row_data = []
        for col in mapper.columns:
            value = clean_string(row[col.name])
            if isinstance(value, (list, dict)):
                value = str(value)
            row_data.append(value)
        ws.append(row_data)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, f'{model_class.__tablename__}.xlsx')
    wb.save(output_path)
    print(f'Данные успешно выгружены в файл: {output_path}')

def clean_string(value):
    """Удаляет из строки невидимые символы ASCII (0-31)"""
    if isinstance(value, str):
        return re.sub(r'[\x00-\x1F]', '', value)
    return value

# Пример использования:
export_table_to_excel(WbStock)