import asyncio
import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Document, Evaluation
from app.schemas import DeleteResponse, DocumentList, DocumentOut, UploadResponse
from app.services import vector_store
from app.services.pdf_service import PDFError, count_pages

log = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])

_CHUNK = 1024 * 1024


@router.post("/upload-pdf", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(response: Response, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    s = get_settings()
    name = Path(file.filename or "document.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .pdf files are accepted")

    s.upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4().hex
    dest = s.upload_dir / f"{doc_id}.pdf"

    # Stream to disk while hashing and enforcing the size limit.
    hasher, size = hashlib.sha256(), 0
    try:
        with dest.open("wb") as out:
            first = True
            while chunk := await file.read(_CHUNK):
                if first and not chunk.startswith(b"%PDF"):
                    raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a PDF")
                first = False
                size += len(chunk)
                if size > s.max_upload_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {s.max_upload_mb} MB"
                    )
                hasher.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
        num_pages = await asyncio.to_thread(count_pages, dest)
    except PDFError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except BaseException:
        dest.unlink(missing_ok=True)
        raise

    digest = hasher.hexdigest()

    async def _existing() -> UploadResponse | None:
        doc = await db.scalar(select(Document).where(Document.sha256 == digest))
        if doc is None:
            return None
        dest.unlink(missing_ok=True)
        response.status_code = status.HTTP_200_OK
        n = await db.scalar(select(func.count()).where(Evaluation.document_id == doc.id))
        return UploadResponse.model_validate(doc).model_copy(update={"duplicate": True, "evaluation_count": n})

    if (dup := await _existing()) is not None:
        return dup

    doc = Document(
        id=doc_id, filename=name, file_path=str(dest), sha256=digest, size_bytes=size, num_pages=num_pages
    )
    db.add(doc)
    try:
        await db.commit()
    except IntegrityError:  # same file uploaded concurrently
        await db.rollback()
        if (dup := await _existing()) is not None:
            return dup
        raise
    return UploadResponse.model_validate(doc)


@router.get("/documents", response_model=DocumentList)
async def list_documents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count()).select_from(Document))
    counts = (
        select(Evaluation.document_id, func.count().label("n"))
        .group_by(Evaluation.document_id)
        .subquery()
    )
    rows = await db.execute(
        select(Document, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.document_id == Document.id)
        .order_by(Document.uploaded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        DocumentOut.model_validate(doc).model_copy(update={"evaluation_count": n}) for doc, n in rows.all()
    ]
    return DocumentList(total=total or 0, items=items)


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    # Vectors first: if this fails the document still exists and can be deleted again.
    try:
        n_collections, n_chunks = await vector_store.delete_document(doc_id)
    except Exception as exc:
        log.exception("ChromaDB delete failed for %s", doc_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Could not delete chunks from ChromaDB: {exc}")

    n_evals = await db.scalar(select(func.count()).where(Evaluation.document_id == doc_id)) or 0
    file_path = Path(doc.file_path)
    await db.execute(delete(Evaluation).where(Evaluation.document_id == doc_id))
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()

    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        log.warning("Could not remove PDF file %s", file_path)

    return DeleteResponse(
        doc_id=doc_id,
        deleted_evaluations=n_evals,
        deleted_collections=n_collections,
        deleted_chunks=n_chunks,
    )
