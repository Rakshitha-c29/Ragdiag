import asyncio

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.schemas import HealthOut
from app.services.models import model_status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(response: Response):
    s = get_settings()
    components: dict = {}
    healthy = True

    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3)
        components["database"] = {"ok": True}
    except Exception as exc:
        healthy = False
        components["database"] = {"ok": False, "error": str(exc)[:200]}

    try:
        from app.services.vector_store import chroma_heartbeat

        await asyncio.to_thread(chroma_heartbeat)
        components["chromadb"] = {"ok": True}
    except Exception as exc:
        healthy = False
        components["chromadb"] = {"ok": False, "error": str(exc)[:200]}

    components["groq"] = {"ok": bool(s.groq_api_key), "configured": bool(s.groq_api_key), "model": s.groq_model}
    if not s.groq_api_key:
        healthy = False

    components["models"] = model_status()

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(status="ok" if healthy else "degraded", components=components)
