"""Failure-type classification with the saved DistilBERT model.

If no model is saved at CLASSIFIER_MODEL_PATH (or it fails to load), a
score-based rule set is used instead and the result is marked source="heuristic".
"""

import asyncio
import logging

from app.config import get_settings
from app.services.models import get_classifier

log = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):  # unknown template fields render as empty
        return ""


def _build_input(question: str, answer: str, chunks: list[str], scores: dict[str, float]) -> str:
    # Default template (must match training):
    # Question: {question} Answer: {answer} Faithfulness: {faithfulness}
    # Completeness: {completeness} Precision: {precision} Context: {context}
    fields = _SafeDict(question=question, answer=answer, context=" ".join(chunks), **scores)
    return get_settings().classifier_input_template.format_map(fields)


def _predict_sync(text: str) -> tuple[str, float, dict[str, float]]:
    clf = get_classifier()
    out = clf(text, truncation=True, max_length=512)
    # Single input with top_k=None returns [{label, score}, ...]; some versions nest it once more.
    if out and isinstance(out[0], list):
        out = out[0]
    probs = {o["label"]: round(float(o["score"]), 4) for o in out}
    best = max(out, key=lambda o: o["score"])
    return best["label"], float(best["score"]), probs


NO_FAILURE = "no_failure"


def all_scores_pass(scores: dict[str, float]) -> bool:
    return all(scores[k] >= t for k, t in get_settings().score_thresholds.items())


def _heuristic(scores: dict[str, float], refused: bool) -> tuple[str, float]:
    t = get_settings().score_thresholds
    cr, fa, co = (scores[k] for k in ("context_relevance", "faithfulness", "completeness"))
    if refused or cr < t["context_relevance"]:
        return "bad_retrieval", 1.0 - cr
    if fa < t["faithfulness"]:
        return "llm_ignored_context", 1.0 - fa
    if co < t["completeness"]:
        return "incomplete_answer", 1.0 - co
    return "bad_retrieval", 1.0 - scores["precision"]  # only precision failed


async def classify(
    question: str, answer: str, chunks: list[str], scores: dict[str, float], refused: bool
) -> dict:
    result = None
    try:
        if get_classifier() is not None:
            text = _build_input(question, answer, chunks, scores)
            label, conf, probs = await asyncio.to_thread(_predict_sync, text)
            result = {"failure_type": label, "confidence": round(conf, 4), "source": "model", "probabilities": probs}
    except Exception:
        log.exception("DistilBERT classifier failed; falling back to heuristic")

    # Every score above its pass mark: no failure, whatever the model predicted.
    # The model's probabilities are kept so its opinion stays visible.
    if not refused and all_scores_pass(scores):
        return {
            "failure_type": NO_FAILURE,
            "confidence": 1.0,
            "source": "thresholds",
            "probabilities": result["probabilities"] if result else {},
        }
    if result:
        return result

    label, conf = _heuristic(scores, refused)
    return {"failure_type": label, "confidence": round(conf, 4), "source": "heuristic", "probabilities": {}}
