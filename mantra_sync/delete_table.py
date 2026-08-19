from core.db.connection import get_db_session
from core.db.models import MantraStocks


def del_table():
    with get_db_session() as db:
        qw = db.query(MantraStocks).delete()



