"""End-to-end evaluation of one question against one document."""

import time
from pathlib import Path

from app.config import get_settings
from app.services import classifier, llm, scoring, vector_store


async def run_evaluation(
    *,
    doc_id: str,
    pdf_path: Path,
    question: str,
    reference: str | None,
    top_k: int | None,
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> dict:
    s = get_settings()
    started = time.perf_counter()
    cfg = {
        "top_k": top_k or s.top_k,
        "chunk_size": chunk_size or s.chunk_size,
        "chunk_overlap": s.chunk_overlap if chunk_overlap is None else chunk_overlap,
        "embedding_model": s.embedding_model,
        "nli_model": s.nli_model,
        "llm_model": s.groq_model,
    }
    if cfg["chunk_overlap"] >= cfg["chunk_size"]:
        cfg["chunk_overlap"] = cfg["chunk_size"] // 5

    # 1-4. Extract (pdfplumber) → chunk (LangChain) → embed (MiniLM) → store (Chroma)
    collection, n_chunks = await vector_store.ensure_indexed(
        doc_id, pdf_path, cfg["chunk_size"], cfg["chunk_overlap"]
    )
    cfg["total_chunks"] = n_chunks

    # 5. Retrieve top-k
    retrieved = await vector_store.retrieve(collection, question, cfg["top_k"])
    texts = [r.text for r in retrieved]

    # 6. Generate answer (Groq)
    answer = await llm.generate_answer(question, texts)

    # 7. Score
    result = await scoring.score_all(question, answer, retrieved, reference)
    scores = result.as_dict()

    # 8. Classify failure (DistilBERT)
    failure = await classifier.classify(
        question, answer, texts, scores, refused=result.details["answer_refused"]
    )

    # 9. Suggest fix (Groq) — not needed when every score passed
    if failure["failure_type"] == classifier.NO_FAILURE:
        fix = {
            "summary": "No fix needed: all four scores are above their thresholds.",
            "root_cause": "",
            "actions": [],
            "suggested_config": {},
        }
    else:
        try:
            fix = await llm.suggest_fix(
                question=question,
                answer=answer,
                chunks=texts,
                scores=scores,
                failure_type=failure["failure_type"],
                config=cfg,
                details=result.details,
            )
        except llm.LLMError as exc:
            fix = {"summary": "Fix suggestion unavailable.", "root_cause": str(exc), "actions": [], "suggested_config": {}}

    chunks_out = [
        {
            "rank": i,
            "chunk_id": r.chunk_id,
            "text": r.text,
            "page": r.page,
            "similarity": round(r.similarity, 4),
            "supports_answer": result.chunk_supports[i - 1],
            "relevant": result.chunk_relevant[i - 1],
        }
        for i, r in enumerate(retrieved, start=1)
    ]

    return {
        "generated_answer": answer,
        "scores": scores,
        "failure": failure,
        "fix_suggestion": fix,
        "retrieved_chunks": chunks_out,
        "score_details": result.details,
        "config": cfg,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
