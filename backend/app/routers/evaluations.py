import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, Evaluation
from app.schemas import EvaluateRequest, EvaluationList, EvaluationOut
from app.services.llm import LLMError
from app.services.pdf_service import PDFError
from app.services.pipeline import run_evaluation

log = logging.getLogger(__name__)
router = APIRouter(tags=["evaluations"])


def to_out(ev: Evaluation) -> EvaluationOut:
    return EvaluationOut(
        evaluation_id=ev.id,
        doc_id=ev.document_id,
        question=ev.question,
        reference_answer=ev.reference_answer,
        generated_answer=ev.generated_answer,
        scores={
            "context_relevance": ev.context_relevance,
            "faithfulness": ev.faithfulness,
            "completeness": ev.completeness,
            "precision": ev.precision,
            "overall": ev.overall_score,
        },
        failure={
            "failure_type": ev.failure_type,
            "confidence": ev.failure_confidence,
            "source": ev.failure_source,
            "probabilities": ev.failure_probabilities,
        },
        fix_suggestion=ev.fix_suggestion,
        retrieved_chunks=ev.retrieved_chunks,
        score_details=ev.score_details,
        config=ev.config,
        latency_ms=ev.latency_ms,
        created_at=ev.created_at,
    )


@router.post("/evaluate", response_model=EvaluationOut)
async def evaluate(req: EvaluateRequest, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, req.doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    pdf_path = Path(doc.file_path)
    if not pdf_path.exists():
        raise HTTPException(status.HTTP_410_GONE, "PDF file is missing on disk; upload it again")

    try:
        r = await run_evaluation(
            doc_id=doc.id,
            pdf_path=pdf_path,
            question=req.question.strip(),
            reference=(req.reference_answer or "").strip() or None,
            top_k=req.top_k,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
    except PDFError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except LLMError as exc:
        log.warning("LLM error during evaluation: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    ev = Evaluation(
        document_id=doc.id,
        question=req.question.strip(),
        reference_answer=req.reference_answer,
        generated_answer=r["generated_answer"],
        context_relevance=r["scores"]["context_relevance"],
        faithfulness=r["scores"]["faithfulness"],
        completeness=r["scores"]["completeness"],
        precision=r["scores"]["precision"],
        overall_score=r["scores"]["overall"],
        failure_type=r["failure"]["failure_type"],
        failure_confidence=r["failure"]["confidence"],
        failure_source=r["failure"]["source"],
        failure_probabilities=r["failure"]["probabilities"],
        fix_suggestion=r["fix_suggestion"],
        retrieved_chunks=r["retrieved_chunks"],
        score_details=r["score_details"],
        config=r["config"],
        latency_ms=r["latency_ms"],
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return to_out(ev)


@router.get("/evaluations/{doc_id}", response_model=EvaluationList)
async def list_evaluations(
    doc_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    failure_type: str | None = Query(None, description="Filter by failure type"),
    db: AsyncSession = Depends(get_db),
):
    if await db.get(Document, doc_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    where = [Evaluation.document_id == doc_id]
    if failure_type:
        where.append(Evaluation.failure_type == failure_type)

    total = await db.scalar(select(func.count()).select_from(Evaluation).where(*where))
    rows = await db.scalars(
        select(Evaluation).where(*where).order_by(Evaluation.created_at.desc()).limit(limit).offset(offset)
    )
    return EvaluationList(doc_id=doc_id, total=total or 0, items=[to_out(e) for e in rows])
