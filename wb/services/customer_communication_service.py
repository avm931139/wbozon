from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import WB_FEEDBACK_RESPONSE_SLA_HOURS, WB_QUESTION_RESPONSE_SLA_HOURS
from app.db import SessionLocal
from app.models import (
    WBCustomerFeedback,
    WBCustomerFeedbackAnswer,
    WBCustomerQuestion,
    WBCustomerQuestionAnswer,
    WBProduct,
)
from wb.customer_communications import CustomerCommunicationsAPI


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _content_quality(text: str, timeliness_points: int | None) -> int:
    normalized = text.strip().casefold()
    content_score = 30 if len(normalized) >= 40 else 20 if len(normalized) >= 15 else 5
    content_score += 15 if any(word in normalized for word in ("спасибо", "здравствуйте", "добрый")) else 0
    generic = normalized in {"спасибо за отзыв", "спасибо за ваш отзыв", "благодарим за отзыв"}
    content_score += 15 if len(normalized) >= 30 and not generic else 0
    if timeliness_points is None:
        return min(round(content_score / 60 * 100), 100)
    return min(content_score + timeliness_points, 100)


def _response_metrics(created: datetime, answer_created: datetime | None, text: str | None, sla_hours: int, pending: bool = True) -> tuple[int | None, bool, int | None]:
    if not text:
        age = max(0, int((datetime.now(timezone.utc) - created).total_seconds()))
        return None, pending and age > sla_hours * 3600, None
    if answer_created is None:
        return None, False, _content_quality(text, timeliness_points=None)
    seconds = max(0, int((answer_created - created).total_seconds()))
    score = _content_quality(text, timeliness_points=40 if seconds <= sla_hours * 3600 else 0)
    return seconds, seconds > sla_hours * 3600, score


class CustomerCommunicationService:
    """Loads and analyzes WB questions and feedbacks. Does not send or edit answers."""

    def __init__(self):
        self.api = CustomerCommunicationsAPI()

    def sync_all(self) -> dict[str, int]:
        unanswered_questions = self.api.questions(False)
        answered_questions = self.api.questions(True)
        unanswered_feedbacks = self.api.feedbacks(False)
        answered_feedbacks = self.api.feedbacks(True)
        return {
            "questions": self._persist_questions(unanswered_questions, False) + self._persist_questions(answered_questions, True),
            "feedbacks": self._persist_feedbacks(unanswered_feedbacks, False) + self._persist_feedbacks(answered_feedbacks, True),
        }

    @staticmethod
    def _persist_questions(items: list[dict[str, Any]], processed: bool) -> int:
        with SessionLocal() as session:
            existing = {x.question_wb_id: x for x in session.query(WBCustomerQuestion).all()}
            answer_versions = {(x.question_id, x.answer_created_date, x.text) for x in session.query(WBCustomerQuestionAnswer).all()}
            products = {x.nm_id: x.id for x in session.query(WBProduct).all()}
            for item in items:
                wb_id = str(item["id"]); row = existing.get(wb_id)
                is_new = row is None
                if row is None:
                    row = WBCustomerQuestion(question_wb_id=wb_id); session.add(row); existing[wb_id] = row
                product = item.get("productDetails") or {}; answer = item.get("answer") or {}; created = _dt(item.get("createdDate")); answer_created = _dt(answer.get("createDate")); answer_text = answer.get("text")
                response_seconds, breached, score = _response_metrics(created, answer_created, answer_text, WB_QUESTION_RESPONSE_SLA_HOURS)
                nm_id = int(product.get("nmId") or 0); row.product_id = products.get(nm_id); row.nm_id = nm_id or None; row.imt_id = product.get("imtId")
                row.text = item.get("text") or ""; row.state = item.get("state"); row.was_viewed = bool(item.get("wasViewed")); row.is_warned = bool(item.get("isWarned")); row.is_processed = processed
                row.is_answered = bool(answer_text); row.created_date = created; row.answer_text = answer_text; row.answer_created_date = answer_created; row.answer_editable = answer.get("editable")
                row.response_seconds = response_seconds; row.sla_hours = WB_QUESTION_RESPONSE_SLA_HOURS; row.sla_breached = breached; row.answer_quality_score = score
                row.product_name = product.get("productName"); row.supplier_article = product.get("supplierArticle"); row.brand_name = product.get("brandName"); row.raw_data = item; row.fetched_at = datetime.utcnow()
                if is_new:
                    session.flush()
                if answer_text and (row.id, answer_created, answer_text) not in answer_versions:
                    session.add(WBCustomerQuestionAnswer(question=row, text=answer_text, answer_created_date=answer_created, editable=answer.get("editable")))
                    answer_versions.add((row.id, answer_created, answer_text))
            session.commit()
        return len(items)

    @staticmethod
    def _persist_feedbacks(items: list[dict[str, Any]], processed: bool) -> int:
        with SessionLocal() as session:
            existing = {x.feedback_wb_id: x for x in session.query(WBCustomerFeedback).all()}
            answer_versions = {(x.feedback_id, x.answer_created_date, x.text) for x in session.query(WBCustomerFeedbackAnswer).all()}
            products = {x.nm_id: x.id for x in session.query(WBProduct).all()}
            for item in items:
                wb_id = str(item["id"]); row = existing.get(wb_id)
                is_new = row is None
                if row is None:
                    row = WBCustomerFeedback(feedback_wb_id=wb_id); session.add(row); existing[wb_id] = row
                product = item.get("productDetails") or {}; answer = item.get("answer") or {}; created = _dt(item.get("createdDate")); answer_created = _dt(answer.get("createDate")); answer_text = answer.get("text")
                nm_id = int(product.get("nmId") or 0); photos = item.get("photoLinks"); video = item.get("video"); tags = item.get("bables")
                is_answerable = bool(item.get("text") or item.get("pros") or item.get("cons") or photos or video or tags)
                response_seconds, breached, score = _response_metrics(created, answer_created, answer_text, WB_FEEDBACK_RESPONSE_SLA_HOURS, pending=is_answerable and not processed)
                row.product_id = products.get(nm_id); row.nm_id = nm_id or None; row.imt_id = product.get("imtId"); row.parent_feedback_wb_id = item.get("parentFeedbackId"); row.child_feedback_wb_id = item.get("childFeedbackId")
                row.text = item.get("text") or ""; row.pros = item.get("pros") or ""; row.cons = item.get("cons") or ""; row.product_valuation = int(item.get("productValuation") or 0); row.user_name = item.get("userName")
                row.state = item.get("state"); row.order_status = item.get("orderStatus"); row.was_viewed = bool(item.get("wasViewed")); row.is_processed = processed
                row.is_answerable = is_answerable; row.is_answered = bool(answer_text); row.created_date = created
                row.answer_text = answer_text; row.answer_created_date = answer_created; row.answer_editable = answer.get("editable"); row.response_seconds = response_seconds
                row.sla_hours = WB_FEEDBACK_RESPONSE_SLA_HOURS; row.sla_breached = breached; row.answer_quality_score = score
                row.product_name = product.get("productName"); row.supplier_article = product.get("supplierArticle"); row.brand_name = product.get("brandName"); row.subject_id = item.get("subjectId"); row.subject_name = item.get("subjectName"); row.color = item.get("color")
                row.photo_links = photos; row.video = video; row.tags = tags; row.last_order_shk_id = item.get("lastOrderShkId"); row.last_order_created_at = _dt(item.get("lastOrderCreatedAt")); row.raw_data = item; row.fetched_at = datetime.utcnow()
                if is_new:
                    session.flush()
                if answer_text and (row.id, answer_created, answer_text) not in answer_versions:
                    session.add(WBCustomerFeedbackAnswer(feedback=row, text=answer_text, answer_created_date=answer_created, editable=answer.get("editable")))
                    answer_versions.add((row.id, answer_created, answer_text))
            session.commit()
        return len(items)

    @staticmethod
    def quality_summary() -> dict[str, Any]:
        with SessionLocal() as session:
            questions = session.query(WBCustomerQuestion).all(); feedbacks = session.query(WBCustomerFeedback).all()
        def metrics(rows: list[Any]) -> dict[str, Any]:
            answered = [x for x in rows if x.is_answered]; response = [x.response_seconds for x in answered if x.response_seconds is not None]; scores = [x.answer_quality_score for x in answered if x.answer_quality_score is not None]
            return {"total": len(rows), "answered": len(answered), "overdue": sum(x.sla_breached and not x.is_answered for x in rows), "sla_breached": sum(x.sla_breached for x in rows), "avg_response_hours": round(sum(response) / len(response) / 3600, 2) if response else None, "avg_quality_score": round(sum(scores) / len(scores), 1) if scores else None}
        return {"questions": metrics(questions), "feedbacks": metrics(feedbacks)}
