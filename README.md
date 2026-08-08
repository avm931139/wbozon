# wbozon

Минимальный каркас Python-проекта с PostgreSQL и SQLAlchemy.

## Структура

- `app/`
  - `__init__.py`
  - `main.py`
  - `config.py`
  - `db.py`
  - `models.py`
- `tests/`
  - `__init__.py`
  - `test_db.py`
- `.env.example`
- `requirements.txt`
- `README.md`

## Зависимости

- Python 3.13
- SQLAlchemy 2.x
- psycopg 3
- python-dotenv
- pytest
- Alembic

## Настройка

1. Скопируйте `.env.example` в `.env`.
2. Установите зависимости:

```bash
python -m pip install -r requirements.txt
```

## Проверка

```bash
python -m pytest tests/test_db.py
```

## Запуск и инициализация БД

```bash
python -m app.main
```
