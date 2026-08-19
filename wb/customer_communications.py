from __future__ import annotations

from typing import Any

from app.config import WB_FEEDBACKS_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient


class CustomerCommunicationsAPI(WBAPIBase):
    """Read-only client for WB customer questions and feedbacks."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_FEEDBACKS_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.questions(**kwargs)

    def questions(self, is_answered: bool, take: int = 5000, **filters: Any) -> list[dict[str, Any]]:
        return self._list("questions", is_answered, take, filters)

    def feedbacks(self, is_answered: bool, take: int = 5000, **filters: Any) -> list[dict[str, Any]]:
        return self._list("feedbacks", is_answered, take, filters)

    def question(self, question_id: str) -> dict[str, Any]:
        return self._one("/api/v1/question", question_id)

    def feedback(self, feedback_id: str) -> dict[str, Any]:
        return self._one("/api/v1/feedback", feedback_id)

    def unanswered_counts(self) -> dict[str, Any]:
        questions = self.client.get("/api/v1/questions/count-unanswered")
        feedbacks = self.client.get("/api/v1/feedbacks/count-unanswered")
        return {
            "questions": questions.get("data", {}) if isinstance(questions, dict) else {},
            "feedbacks": feedbacks.get("data", {}) if isinstance(feedbacks, dict) else {},
        }

    def _list(self, kind: str, is_answered: bool, take: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        if not 1 <= take <= 10000:
            raise ValueError("take must be between 1 and 10000")
        params = {"isAnswered": str(is_answered).lower(), "take": take, "skip": 0, "order": "dateDesc", **filters}
        payload = self.client.get(f"/api/v1/{kind}", params=params, retries=8)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        rows = data.get(kind, []) if isinstance(data, dict) else []
        return [row for row in rows if isinstance(row, dict)]

    def _one(self, path: str, item_id: str) -> dict[str, Any]:
        payload = self.client.get(path, params={"id": item_id}, retries=8)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}
