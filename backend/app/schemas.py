from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------- Documents ----------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    size_bytes: int
    num_pages: int
    uploaded_at: datetime
    evaluation_count: int = 0


class UploadResponse(DocumentOut):
    duplicate: bool = False


class DocumentList(BaseModel):
    total: int
    items: list[DocumentOut]


class DeleteResponse(BaseModel):
    doc_id: str
    deleted_evaluations: int
    deleted_collections: int
    deleted_chunks: int


# ---------- Evaluation ----------

class EvaluateRequest(BaseModel):
    doc_id: str
    question: str = Field(min_length=3, max_length=2000)
    reference_answer: str | None = Field(
        default=None,
        max_length=8000,
        description="Optional ground-truth answer. If set, completeness is measured against it with NLI.",
    )
    top_k: int | None = Field(default=None, ge=1, le=20)
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def _overlap_lt_size(self):
        if self.chunk_size and self.chunk_overlap is not None and self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class RetrievedChunk(BaseModel):
    rank: int
    chunk_id: str
    text: str
    page: int | None
    similarity: float = Field(description="Cosine similarity between question and chunk")
    supports_answer: bool = Field(description="At least one answer claim is entailed by this chunk")
    relevant: bool = Field(description="Counted as relevant for the precision score")


class Scores(BaseModel):
    context_relevance: float
    faithfulness: float
    completeness: float
    precision: float
    overall: float


class FailureClassification(BaseModel):
    failure_type: str
    confidence: float
    source: str = Field(description="'model' (DistilBERT) or 'heuristic' fallback")
    probabilities: dict[str, float] = {}


class FixSuggestion(BaseModel):
    summary: str
    root_cause: str
    actions: list[str]
    suggested_config: dict[str, Any] = {}


class EvaluationOut(BaseModel):
    evaluation_id: str
    doc_id: str
    question: str
    reference_answer: str | None
    generated_answer: str
    scores: Scores
    failure: FailureClassification
    fix_suggestion: FixSuggestion
    retrieved_chunks: list[RetrievedChunk]
    score_details: dict[str, Any]
    config: dict[str, Any]
    latency_ms: int
    created_at: datetime


class EvaluationList(BaseModel):
    doc_id: str
    total: int
    items: list[EvaluationOut]


# ---------- Health ----------

class HealthOut(BaseModel):
    status: str
    components: dict[str, Any]
