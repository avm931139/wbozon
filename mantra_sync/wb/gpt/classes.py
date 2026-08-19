import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from wb.gpt.gpt_client import GPTClient
from core.db.models import GPTModels


logger = logging.getLogger(__name__)


class ModelSaver:
    """Класс для сохранения данных моделей из API в базу данных"""

    def __init__(self, db_session: Session, gpt_client: Optional[GPTClient] = None):
        """
        Инициализация сохранщика моделей

        Args:
            db_session: Сессия SQLAlchemy для работы с БД
            gpt_client: Клиент GPT для получения данных (опционально)
        """
        self.db = db_session
        self.gpt = gpt_client or GPTClient()

    def save_models_from_api(self, models_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Получить модели из API и сохранить в БД

        Args:
            models_data: Список моделей (если не указан, загружается из API через self.gpt)

        Returns:
            Словарь со статистикой сохранения
        """
        stats = {
            'added': 0,
            'updated': 0,
            'errors': 0,
            'total': 0,
            'details': []
        }

        try:
            # Получаем данные моделей, если не переданы
            if models_data is None:
                logger.info("Загрузка моделей из API...")
                models_data = self.gpt.get_models()
                logger.info(f"Загружено {len(models_data)} моделей из API")

            # Сохраняем каждую модель
            for model_data in models_data:
                try:
                    result = self._save_single_model(model_data)
                    stats['total'] += 1

                    if result['action'] == 'added':
                        stats['added'] += 1
                    elif result['action'] == 'updated':
                        stats['updated'] += 1

                    stats['details'].append(result)

                except Exception as e:
                    stats['errors'] += 1
                    error_detail = {
                        'model_id': model_data.get('id', 'unknown'),
                        'action': 'error',
                        'error': str(e)
                    }
                    stats['details'].append(error_detail)
                    logger.error(f"Ошибка при сохранении модели {model_data.get('id')}: {e}")

            # Коммитим все изменения
            self.db.commit()
            logger.info(
                f"Сохранение завершено: добавлено {stats['added']}, обновлено {stats['updated']}, ошибок {stats['errors']}")

        except Exception as e:
            self.db.rollback()
            logger.error(f"Критическая ошибка при сохранении моделей: {e}")
            raise

        return stats

    def _save_single_model(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Сохранить одну модель (создать или обновить)

        Args:
            model_data: Данные модели из API

        Returns:
            Словарь с результатом операции
        """
        model_id = model_data.get('id')
        if not model_id:
            raise ValueError("Модель не содержит поле 'id'")

        # Проверяем существование модели
        existing_model = self.db.query(GPTModels).filter(GPTModels.id == model_id).first()

        # Подготавливаем данные
        model_dict = self._prepare_model_data(model_data)

        if existing_model:
            return self._update_existing_model(existing_model, model_dict)
        else:
            return self._create_new_model(model_dict)

    def _prepare_model_data(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Подготовка данных модели для сохранения в БД
        """
        # Определяем тип модели
        model_type = self._determine_model_type(model_data)

        # Определяем флаг opencode
        opencode = self._is_opencode_model(model_data.get('id', ''))

        prepared = {
            'id': model_data.get('id'),
            'object': model_data.get('object', 'model'),
            'title': model_data.get('title', '').replace('\xa0', ' '),  # Заменяем неразрывные пробелы
            'created': model_data.get('created', int(datetime.now().timestamp())),
            'max_capacity': model_data.get('max_capacity', 4096),
            'max_completion_tokens': model_data.get('max_completion_tokens'),
            'cost_context': model_data.get('cost_context', '0.00'),
            'cost_completion': model_data.get('cost_completion', '0.00'),
            'type': model_type,
            'opencode': opencode,
            'is_active': True,
            'updated_at': datetime.utcnow()
        }

        # Приводим цены к строке с 4 знаками после запятой
        try:
            prepared['cost_context'] = f"{float(prepared['cost_context']):.4f}"
            prepared['cost_completion'] = f"{float(prepared['cost_completion']):.4f}"
        except (ValueError, TypeError):
            pass

        return prepared

    def _determine_model_type(self, model_data: Dict[str, Any]) -> str:
        """Определить тип модели"""
        model_id = model_data.get('id', '').lower()
        title = model_data.get('title', '').lower()

        if 'embedding' in model_id or 'embedding' in title:
            return 'EMBEDDING'
        if 'moderation' in model_id or 'moderation' in title:
            return 'MODERATION'
        if 'vision' in model_id or 'vision' in title or 'omni' in model_id:
            return 'VISION'

        return 'TEXT'

    def _is_opencode_model(self, model_id: str) -> bool:
        """Определить, является ли модель открытой"""
        open_models = ['llama', 'mistral', 'qwen', 'deepseek', 'mixtral', 'ministral', 'nemotron', 'gemma']
        model_id_lower = model_id.lower()
        return any(open_model in model_id_lower for open_model in open_models)

    def _create_new_model(self, model_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Создать новую запись модели"""
        new_model = GPTModels(
            id=model_dict['id'],
            object=model_dict['object'],
            title=model_dict['title'],
            created=model_dict['created'],
            max_capacity=model_dict['max_capacity'],
            max_completion_tokens=model_dict.get('max_completion_tokens'),
            cost_context=model_dict['cost_context'],
            cost_completion=model_dict['cost_completion'],
            type=model_dict['type'],
            opencode=model_dict['opencode'],
            is_active=model_dict['is_active'],
            created_at=datetime.utcnow(),
            updated_at=model_dict['updated_at']
        )

        self.db.add(new_model)
        self.db.flush()

        logger.info(f"Добавлена новая модель: {new_model.id} - {new_model.title}")

        return {
            'model_id': new_model.id,
            'action': 'added',
            'title': new_model.title,
            'type': new_model.type
        }

    def _update_existing_model(self, existing_model: GPTModels, model_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить существующую модель"""
        changes = []

        # Поля для обновления
        updatable_fields = ['title', 'max_capacity', 'max_completion_tokens',
                            'cost_context', 'cost_completion', 'type', 'opencode']

        for field in updatable_fields:
            if field in model_dict:
                current_value = getattr(existing_model, field)
                new_value = model_dict[field]
                if current_value != new_value:
                    setattr(existing_model, field, new_value)
                    changes.append(f"{field}: {current_value} -> {new_value}")

        if changes:
            existing_model.updated_at = datetime.utcnow()
            self.db.flush()
            logger.info(f"Обновлена модель {existing_model.id}: {', '.join(changes)}")

            return {
                'model_id': existing_model.id,
                'action': 'updated',
                'title': existing_model.title,
                'changes': changes,
                'type': existing_model.type
            }
        else:
            return {
                'model_id': existing_model.id,
                'action': 'no_change',
                'title': existing_model.title,
                'type': existing_model.type
            }

import time
from core.db.connection import get_db_session
from core.db.models import GPTChatLog


class GPTLogWriter:

    @staticmethod
    def save(product_id_ms: str, response: dict):
        """
        Сохраняет ответ GPT API в БД
        """

        choice = response["choices"][0]
        message = choice["message"]

        usage = response.get("usage", {})

        log = GPTChatLog(
            product_id_ms=product_id_ms,

            model=response.get("model"),
            content=message.get("content"),

            response_id=response.get("id"),
            object=response.get("object"),
            created=response.get("created"),
            role=message.get("role"),

            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),

            prompt_cost=usage.get("prompt_cost"),
            completion_cost=usage.get("completion_cost"),
            total_cost=usage.get("total_cost"),

            raw_response=response,

            created_at=int(time.time())
        )

        with get_db_session() as db:
            db.add(log)
            db.commit()