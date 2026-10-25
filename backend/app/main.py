import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, init_db
from app.routers import documents, evaluations, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ragdiag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    if s.warm_models:
        from app.services.models import warm_all

        log.info("Loading models...")
        await asyncio.to_thread(warm_all)
        log.info("Models loaded")
    yield
    await engine.dispose()


app = FastAPI(
    title="RAGDiag API",
    description="Evaluate and diagnose RAG pipelines on your PDFs.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(evaluations.router)
