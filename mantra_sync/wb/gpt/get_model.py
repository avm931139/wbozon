from wb.gpt.gpt_client import GPTClient
from wb.gpt.classes import ModelSaver
from core.db.connection import get_db_session

gpt = GPTClient()

models = gpt.get_models()
with get_db_session() as session:
    ModelSaver(session).save_models_from_api(models)

