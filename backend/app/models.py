import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    num_pages: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )

    question: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_answer: Mapped[str] = mapped_column(Text)

    context_relevance: Mapped[float] = mapped_column(Float)
    faithfulness: Mapped[float] = mapped_column(Float)
    completeness: Mapped[float] = mapped_column(Float)
    precision: Mapped[float] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float)

    failure_type: Mapped[str] = mapped_column(String(64), index=True)
    failure_confidence: Mapped[float] = mapped_column(Float)
    failure_source: Mapped[str] = mapped_column(String(16))
    failure_probabilities: Mapped[dict] = mapped_column(JSON)
    fix_suggestion: Mapped[dict] = mapped_column(JSON)

    retrieved_chunks: Mapped[list] = mapped_column(JSON)
    score_details: Mapped[dict] = mapped_column(JSON)
    config: Mapped[dict] = mapped_column(JSON)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    document: Mapped[Document] = relationship(back_populates="evaluations")
