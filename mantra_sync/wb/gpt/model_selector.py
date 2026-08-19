from dataclasses import dataclass
from typing import Optional, List
from sqlalchemy.orm import Session
from models import GPTModels


@dataclass
class ModelSelectionConfig:
    default_model_id: str = "gpt-5.4"
    max_cost_per_1k_context: Optional[float] = None
    max_context_size: Optional[int] = None
    require_active: bool = True


class GPTModelSelector:
    """
    Выбор GPT модели для обработки товаров
    """

    def __init__(self, session: Session, config: ModelSelectionConfig = ModelSelectionConfig()):
        self.session = session
        self.config = config

    def get_available_models(self) -> List[GPTModels]:
        query = self.session.query(GPTModels)

        if self.config.require_active:
            query = query.filter(GPTModels.is_active == True)

        return query.order_by(GPTModels.cost_context.asc()).all()

    def select_model_interactive(self) -> GPTModels:
        """
        Интерактивный выбор модели:
        Enter → default (gpt-5.4)
        """

        models = self.get_available_models()

        print("\n=== AVAILABLE GPT MODELS ===")
        for i, m in enumerate(models, 1):
            print(f"{i}. {m.id} | {m.title} | ctx={m.max_capacity} | cost={m.cost_context}")

        print("\nEnter → default (gpt-5.4)")

        user_input = input("Select model: ").strip()

        # DEFAULT
        if not user_input:
            return self._get_default_model()

        # numeric selection
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(models):
                return models[idx]

        # by id
        for m in models:
            if m.id == user_input:
                return m

        print("Invalid selection → fallback to default")
        return self._get_default_model()

    def _get_default_model(self) -> GPTModels:
        model = (
            self.session.query(GPTModels)
            .filter(GPTModels.id == self.config.default_model_id)
            .first()
        )

        if model:
            return model

        # fallback: cheapest active model
        return (
            self.session.query(GPTModels)
            .filter(GPTModels.is_active == True)
            .order_by(GPTModels.cost_context.asc())
            .first()
        )

    # ----------------------------
    # ПАРАМЕТРЫ ДЛЯ GPT ЗАПРОСА
    # ----------------------------

    def build_llm_params(self, model: GPTModels) -> dict:
        """
        Генерация параметров для запроса к LLM
        (важно для качества сопоставления характеристик)
        """

        return {
            "model": model.id,

            # критично для задач сопоставления товаров
            "temperature": 0.2,      # низкая → меньше фантазий, больше точности
            "top_p": 0.9,

            # контроль длины ответа
            "max_tokens": min(model.max_completion_tokens or 2000, 2000),

            # стабильность (если API поддерживает)
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,

            # режим детерминизма
            "response_format": {"type": "json_object"}
        }