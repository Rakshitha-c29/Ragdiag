from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — relative paths and .env resolve from here, whatever the working directory.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "RAGDiag"

    # Database
    database_url: str = "postgresql+asyncpg://ragdiag:ragdiag@localhost:5432/ragdiag"
    db_echo: bool = False

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_s: float = 60.0

    # Storage
    upload_dir: Path = Path("./data/uploads")
    chroma_dir: Path = Path("./data/chroma")
    max_upload_mb: int = 25

    # Models
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    nli_model: str = "cross-encoder/nli-deberta-v3-base"
    classifier_model_path: Path = Path("./models/failure_classifier")
    classifier_input_template: str = (
        "Question: {question} Answer: {answer} Faithfulness: {faithfulness} "
        "Completeness: {completeness} Precision: {precision} Context: {context}"
    )
    device: str = ""  # "", "cpu", "cuda" — empty means auto-detect

    # Pipeline defaults
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 5

    # Scoring thresholds
    nli_entail_threshold: float = 0.5
    chunk_relevance_threshold: float = 0.5  # question/chunk cosine sim for precision

    # Pass marks per score. All four passing => failure_type "no_failure".
    # Keep in sync with SCORE_META in frontend/src/lib/format.js.
    threshold_context_relevance: float = 0.35
    threshold_faithfulness: float = 0.6
    threshold_completeness: float = 0.5
    threshold_precision: float = 0.4

    @property
    def score_thresholds(self) -> dict[str, float]:
        return {
            "context_relevance": self.threshold_context_relevance,
            "faithfulness": self.threshold_faithfulness,
            "completeness": self.threshold_completeness,
            "precision": self.threshold_precision,
        }

    warm_models: bool = False

    @field_validator("upload_dir", "chroma_dir", "classifier_model_path")
    @classmethod
    def _anchor(cls, v: Path) -> Path:
        return v if v.is_absolute() else (BASE_DIR / v).resolve()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
