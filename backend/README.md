# RAGDiag backend

FastAPI service that runs a RAG pipeline over an uploaded PDF, scores the result on four dimensions, classifies the failure type, and suggests a fix.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

docker compose up -d            # PostgreSQL on localhost:5432
copy .env.example .env          # then set GROQ_API_KEY
uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

Tables are created automatically on startup. The first `/evaluate` call downloads MiniLM (~90 MB) and DeBERTa NLI (~700 MB) from Hugging Face. Set `WARM_MODELS=true` to load them at startup instead.

### Failure classifier

Put your fine-tuned DistilBERT (the output of `model.save_pretrained()` + `tokenizer.save_pretrained()`) in `models/failure_classifier/`, so that `models/failure_classifier/config.json` exists.

- It is loaded with the HuggingFace `text-classification` pipeline. Labels are fixed in `app/services/models.py` (`FAILURE_LABELS`): `0=bad_retrieval, 1=hallucination_in_context, 2=llm_ignored_context, 3=incomplete_answer`. A model with fewer outputs uses the first N labels and logs a warning.
- Input format (`CLASSIFIER_INPUT_TEMPLATE`): `Question: {question} Answer: {answer} Faithfulness: {faithfulness} Completeness: {completeness} Precision: {precision} Context: {context}`. Inputs are truncated to 512 tokens.
- If no model is found or it fails to load, a rule-based fallback is used. The response shows which one ran in `failure.source` (`"model"` or `"heuristic"`).
- Relative paths in `.env` are resolved from `backend/`, so it doesn't matter which folder you start uvicorn from.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/upload-pdf` | Multipart `file`. Saves the PDF and returns its `id`. Re-uploading the same file returns the existing document with `duplicate: true`. |
| POST | `/evaluate` | Runs the full pipeline and stores the result. |
| GET | `/evaluations/{doc_id}` | Past evaluations for a document. `limit`, `offset`, `failure_type` filters. |
| GET | `/documents` | Uploaded documents with evaluation counts. |
| DELETE | `/documents/{doc_id}` | Deletes the document, its evaluations, all of its ChromaDB chunks (every chunk-size setting) and the stored PDF. |
| GET | `/health` | DB, ChromaDB, Groq config and model load status. Returns 503 when degraded. |

### `/evaluate` request

```json
{
  "doc_id": "3f2c...",
  "question": "What is the refund window?",
  "reference_answer": "30 days from delivery.",
  "top_k": 5,
  "chunk_size": 800,
  "chunk_overlap": 120
}
```

Only `doc_id` and `question` are required.

### Pipeline

1. Extract text per page with **pdfplumber**
2. Chunk with LangChain `RecursiveCharacterTextSplitter` (chunks keep their page number)
3. Embed with **all-MiniLM-L6-v2** (normalised)
4. Store in **ChromaDB** (cosine). One collection per document × chunk settings, built on first use and reused afterwards
5. Retrieve top-k chunks
6. Generate an answer with **Groq**, restricted to the retrieved context
7. Score (all 0–1):
   - **context_relevance**: mean question↔chunk cosine similarity
   - **faithfulness**: share of answer sentences entailed by at least one chunk (**DeBERTa NLI**)
   - **completeness**: with `reference_answer`, share of reference sentences entailed by the answer (NLI). Without it, Groq grades how fully the question is answered
   - **precision**: rank-weighted average precision; a chunk counts as relevant if it supports an answer sentence or its similarity to the question is ≥ `CHUNK_RELEVANCE_THRESHOLD`
8. Classify the failure type with the saved **DistilBERT** model
9. Ask **Groq** for a root cause, fix actions and suggested config changes

If the model replies "I don't know based on the provided context.", faithfulness is 1 (nothing was made up) and completeness is 0.

### Response shape

```json
{
  "evaluation_id": "...",
  "doc_id": "...",
  "question": "...",
  "generated_answer": "...",
  "scores": {"context_relevance": 0.61, "faithfulness": 0.75, "completeness": 0.8, "precision": 0.92, "overall": 0.77},
  "failure": {"failure_type": "hallucination", "confidence": 0.88, "source": "model", "probabilities": {...}},
  "fix_suggestion": {"summary": "...", "root_cause": "...", "actions": ["..."], "suggested_config": {"top_k": 8}},
  "retrieved_chunks": [{"rank": 1, "chunk_id": "...", "text": "...", "page": 3, "similarity": 0.71, "supports_answer": true, "relevant": true}],
  "score_details": {"faithfulness": {"claims": [...], "unsupported_claims": [...]}, "completeness": {...}, "precision": {...}},
  "config": {"top_k": 5, "chunk_size": 800, "chunk_overlap": 120, "...": "..."},
  "latency_ms": 4210,
  "created_at": "..."
}
```

## Notes

- Schema changes: tables are created with `create_all`, which does not alter existing tables. Add Alembic before the schema starts changing in production.
- Uploaded PDFs live in `UPLOAD_DIR`, vectors in `CHROMA_DIR`.
