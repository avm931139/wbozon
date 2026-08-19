"""add read-only customer questions and feedbacks

Revision ID: 20260809_customer_communications
Revises: 20260809_add_table_comments
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_customer_communications"
down_revision = "20260809_add_table_comments"
branch_labels = None
depends_on = None


def _indexes(table: str, columns: tuple[str, ...], unique: tuple[str, ...] = ()) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column], unique=column in unique)


def upgrade() -> None:
    op.create_table("wb_customer_questions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("question_wb_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id")), sa.Column("nm_id", sa.BigInteger()), sa.Column("imt_id", sa.BigInteger()),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("state", sa.String()), sa.Column("was_viewed", sa.Boolean(), nullable=False), sa.Column("is_warned", sa.Boolean(), nullable=False),
        sa.Column("is_processed", sa.Boolean(), nullable=False), sa.Column("is_answered", sa.Boolean(), nullable=False), sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer_text", sa.Text()), sa.Column("answer_created_date", sa.DateTime(timezone=True)), sa.Column("answer_editable", sa.Boolean()),
        sa.Column("response_seconds", sa.BigInteger()), sa.Column("sla_hours", sa.Integer(), nullable=False), sa.Column("sla_breached", sa.Boolean(), nullable=False), sa.Column("answer_quality_score", sa.Integer()),
        sa.Column("product_name", sa.String()), sa.Column("supplier_article", sa.String()), sa.Column("brand_name", sa.String()), sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        comment="Вопросы покупателей Wildberries и метрики качества ответа продавца.")
    _indexes("wb_customer_questions", ("id", "question_wb_id", "product_id", "nm_id", "state", "is_processed", "is_answered", "created_date", "answer_created_date", "sla_breached", "answer_quality_score"), ("question_wb_id",))

    op.create_table("wb_customer_question_answers",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("question_id", sa.Integer(), sa.ForeignKey("wb_customer_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("answer_created_date", sa.DateTime(timezone=True)), sa.Column("editable", sa.Boolean()), sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("question_id", "answer_created_date", "text", name="uq_wb_question_answer_version"),
        comment="История полученных из WB версий ответов продавца на вопросы покупателей.")
    _indexes("wb_customer_question_answers", ("id", "question_id"))

    op.create_table("wb_customer_feedbacks",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("feedback_wb_id", sa.String(), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("wb_products.id")),
        sa.Column("nm_id", sa.BigInteger()), sa.Column("imt_id", sa.BigInteger()), sa.Column("parent_feedback_wb_id", sa.String()), sa.Column("child_feedback_wb_id", sa.String()),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("pros", sa.Text(), nullable=False), sa.Column("cons", sa.Text(), nullable=False), sa.Column("product_valuation", sa.Integer(), nullable=False),
        sa.Column("user_name", sa.String()), sa.Column("state", sa.String()), sa.Column("order_status", sa.String()), sa.Column("was_viewed", sa.Boolean(), nullable=False),
        sa.Column("is_processed", sa.Boolean(), nullable=False), sa.Column("is_answerable", sa.Boolean(), nullable=False), sa.Column("is_answered", sa.Boolean(), nullable=False), sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answer_text", sa.Text()), sa.Column("answer_created_date", sa.DateTime(timezone=True)), sa.Column("answer_editable", sa.Boolean()), sa.Column("response_seconds", sa.BigInteger()),
        sa.Column("sla_hours", sa.Integer(), nullable=False), sa.Column("sla_breached", sa.Boolean(), nullable=False), sa.Column("answer_quality_score", sa.Integer()),
        sa.Column("product_name", sa.String()), sa.Column("supplier_article", sa.String()), sa.Column("brand_name", sa.String()), sa.Column("subject_id", sa.BigInteger()), sa.Column("subject_name", sa.String()), sa.Column("color", sa.String()),
        sa.Column("photo_links", sa.JSON()), sa.Column("video", sa.JSON()), sa.Column("tags", sa.JSON()), sa.Column("last_order_shk_id", sa.BigInteger()), sa.Column("last_order_created_at", sa.DateTime(timezone=True)),
        sa.Column("raw_data", sa.JSON(), nullable=False), sa.Column("fetched_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        comment="Отзывы покупателей Wildberries, оценки товара и метрики ответа продавца.")
    _indexes("wb_customer_feedbacks", ("id", "feedback_wb_id", "product_id", "nm_id", "product_valuation", "state", "is_processed", "is_answerable", "is_answered", "created_date", "answer_created_date", "sla_breached", "answer_quality_score"), ("feedback_wb_id",))

    op.create_table("wb_customer_feedback_answers",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("feedback_id", sa.Integer(), sa.ForeignKey("wb_customer_feedbacks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("answer_created_date", sa.DateTime(timezone=True)), sa.Column("editable", sa.Boolean()), sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("feedback_id", "answer_created_date", "text", name="uq_wb_feedback_answer_version"),
        comment="История полученных из WB версий ответов продавца на отзывы покупателей.")
    _indexes("wb_customer_feedback_answers", ("id", "feedback_id"))


def downgrade() -> None:
    for table in ("wb_customer_feedback_answers", "wb_customer_feedbacks", "wb_customer_question_answers", "wb_customer_questions"):
        op.drop_table(table)
