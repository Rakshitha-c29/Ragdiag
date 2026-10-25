"""Lazy, process-wide singletons for the ML models.

Heavy libraries (torch, transformers, sentence-transformers) are imported on
first use so the API starts quickly and /health works without them loaded.
"""

import logging
import threading
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)
_lock = threading.Lock()


def _device() -> str:
    s = get_settings()
    if s.device:
        return s.device
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def get_embedder():
    from sentence_transformers import SentenceTransformer

    with _lock:
        return SentenceTransformer(get_settings().embedding_model, device=_device())


@lru_cache(maxsize=1)
def get_nli():
    """Returns (tokenizer, model, label_index) where label_index maps
    'entailment' / 'neutral' / 'contradiction' to logit positions."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    name = get_settings().nli_model
    with _lock:
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForSequenceClassification.from_pretrained(name).to(_device()).eval()

    label_index: dict[str, int] = {}
    for idx, label in model.config.id2label.items():
        low = label.lower()
        for key in ("entailment", "neutral", "contradiction"):
            if key[:6] in low:
                label_index[key] = int(idx)
    if "entailment" not in label_index:
        raise RuntimeError(f"NLI model {name} has no entailment label: {model.config.id2label}")
    return tok, model, label_index


FAILURE_LABELS = {
    0: "bad_retrieval",
    1: "hallucination_in_context",
    2: "llm_ignored_context",
    3: "incomplete_answer",
}


@lru_cache(maxsize=1)
def get_classifier():
    """HuggingFace text-classification pipeline for the saved DistilBERT
    failure classifier, or None if no model is saved at CLASSIFIER_MODEL_PATH."""
    path = get_settings().classifier_model_path
    if not (path / "config.json").exists():
        log.warning("No failure classifier at %s; using heuristic fallback", path.resolve())
        return None

    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    with _lock:
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path)

    n = model.config.num_labels
    if n > len(FAILURE_LABELS):
        raise RuntimeError(f"Classifier has {n} outputs but only {len(FAILURE_LABELS)} labels are defined")
    if n < len(FAILURE_LABELS):
        log.warning(
            "Classifier was trained with %d classes; it cannot predict: %s",
            n, ", ".join(FAILURE_LABELS[i] for i in range(n, len(FAILURE_LABELS))),
        )
    model.config.id2label = {i: FAILURE_LABELS[i] for i in range(n)}
    model.config.label2id = {v: k for k, v in model.config.id2label.items()}

    device = _device()
    return pipeline(
        "text-classification",
        model=model,
        tokenizer=tok,
        device=0 if device == "cuda" else -1,
        top_k=None,  # return scores for every label
    )


def model_status() -> dict:
    return {
        "embedder_loaded": get_embedder.cache_info().currsize > 0,
        "nli_loaded": get_nli.cache_info().currsize > 0,
        "classifier_loaded": get_classifier.cache_info().currsize > 0,
        "classifier_available": (get_settings().classifier_model_path / "config.json").exists(),
    }


def warm_all() -> None:
    get_embedder()
    get_nli()
    get_classifier()
