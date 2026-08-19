import os
import requests
from typing import List, Dict, Any, Optional
from settings import Config



class GPTClient:
    def __init__(
            self,
            api_key: Optional[str] = Config.API_TOKEN_GPT_TUN,
            base_url: str = "https://gptunnel.ru/v1",
            default_model: str = "gpt-5.4",
            default_temperature: float = 0.2,
            default_max_tokens: Optional[int] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url

        self.default_model = default_model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    # -------------------------------------------------
    # CHAT COMPLETION (REFINED)
    # -------------------------------------------------

    def chat_completion(
            self,
            messages: List[Dict[str, str]],
            model: Optional[str] = None,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            **kwargs
    ) -> Dict[str, Any]:
        """
        Универсальный вызов Chat Completion с fallback-логикой
        """

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": (
                self.default_temperature if temperature is None else temperature
            ),
            **kwargs
        }

        # max_tokens fallback
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        elif self.default_max_tokens is not None:
            payload["max_tokens"] = self.default_max_tokens

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=60
            )

            response.raise_for_status()
            data = response.json()

            return data

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"GPT API request failed: {e}") from e

def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить информацию о конкретной модели

    Args:
        model_id: ID модели (например, "gpt-4o-mini")

    Returns:
        Информация о модели или None, если модель не найдена
    """
    models = self.get_models()
    for model in models:
        if model.get("id") == model_id:
            return model
    return None