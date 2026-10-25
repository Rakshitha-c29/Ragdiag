"""Chunking (LangChain), embedding (MiniLM) and ChromaDB storage/retrieval.

Each (document, chunk_size, chunk_overlap) combination gets its own Chroma
collection, so you can evaluate the same PDF under different chunking setups.
Indexing happens on the first /evaluate call for that combination and is
reused afterwards.
"""

import asyncio
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.services.models import get_embedder
from app.services.pdf_service import extract_pages

_index_locks: dict[str, asyncio.Lock] = {}


@dataclass
class Retrieved:
    chunk_id: str
    text: str
    page: int | None
    similarity: float


@lru_cache(maxsize=1)
def get_chroma():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    path = get_settings().chroma_dir
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
    )


_chroma_lock = threading.Lock()


def collection_name(doc_id: str, chunk_size: int, chunk_overlap: int) -> str:
    # Chroma names: 3-63 chars, [a-zA-Z0-9._-]
    return f"d_{doc_id}_{chunk_size}_{chunk_overlap}"


def embed(texts: list[str]):
    """L2-normalised embeddings as a numpy array."""
    return get_embedder().encode(
        texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )


def _index_sync(pdf_path: Path, name: str, chunk_size: int, chunk_overlap: int) -> int:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    client = get_chroma()
    with _chroma_lock:
        existing = client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
        if existing.count() > 0:
            return existing.count()

    pages = extract_pages(pdf_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    docs = splitter.create_documents(
        texts=[p.text for p in pages], metadatas=[{"page": p.page} for p in pages]
    )
    docs = [d for d in docs if d.page_content.strip()]
    texts = [d.page_content for d in docs]
    vectors = embed(texts)

    ids = [f"{name}-{i}" for i in range(len(texts))]
    metas = [{"page": d.metadata["page"], "chunk_index": i} for i, d in enumerate(docs)]

    collection = client.get_collection(name)
    batch = 1000
    for start in range(0, len(ids), batch):
        end = start + batch
        collection.add(
            ids=ids[start:end],
            documents=texts[start:end],
            embeddings=vectors[start:end].tolist(),
            metadatas=metas[start:end],
        )
    return len(ids)


async def ensure_indexed(doc_id: str, pdf_path: Path, chunk_size: int, chunk_overlap: int) -> tuple[str, int]:
    """Extract → chunk → embed → store, unless already done. Returns (collection, n_chunks)."""
    name = collection_name(doc_id, chunk_size, chunk_overlap)
    lock = _index_locks.setdefault(name, asyncio.Lock())
    async with lock:
        n = await asyncio.to_thread(_index_sync, pdf_path, name, chunk_size, chunk_overlap)
    return name, n


def _retrieve_sync(name: str, question: str, top_k: int) -> list[Retrieved]:
    qvec = embed([question])[0]
    collection = get_chroma().get_collection(name)
    res = collection.query(
        query_embeddings=[qvec.tolist()],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    out: list[Retrieved] = []
    for cid, text, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append(
            Retrieved(
                chunk_id=cid,
                text=text,
                page=(meta or {}).get("page"),
                similarity=float(1.0 - dist),  # cosine space: distance = 1 - cos
            )
        )
    return out


async def retrieve(name: str, question: str, top_k: int) -> list[Retrieved]:
    return await asyncio.to_thread(_retrieve_sync, name, question, top_k)


def _delete_collections_sync(doc_id: str) -> tuple[int, int]:
    client = get_chroma()
    prefix = f"d_{doc_id}_"
    collections = chunks = 0
    with _chroma_lock:
        for col in client.list_collections():
            name = col if isinstance(col, str) else col.name  # str in some Chroma versions
            if name.startswith(prefix):
                chunks += client.get_collection(name).count()
                client.delete_collection(name)
                collections += 1
    return collections, chunks


async def delete_document(doc_id: str) -> tuple[int, int]:
    """Drop every collection (all chunk settings) for a document. Returns (collections, chunks)."""
    prefix = f"d_{doc_id}_"
    names = [n for n in _index_locks if n.startswith(prefix)]
    locks = [_index_locks[n] for n in names]
    # Wait for any in-progress indexing of this document to finish first.
    for lock in locks:
        await lock.acquire()
    try:
        return await asyncio.to_thread(_delete_collections_sync, doc_id)
    finally:
        for lock in locks:
            lock.release()
        for n in names:
            _index_locks.pop(n, None)


def chroma_heartbeat() -> int:
    return get_chroma().heartbeat()
