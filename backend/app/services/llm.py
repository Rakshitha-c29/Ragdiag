"""Groq calls: answer generation, completeness judging, fix suggestion."""

import json
import logging
import re
from functools import lru_cache
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

REFUSAL = "I don't know based on the provided context."


class LLMError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client():
    from groq import AsyncGroq

    s = get_settings()
    if not s.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set")
    return AsyncGroq(api_key=s.groq_api_key, timeout=s.groq_timeout_s, max_retries=2)


async def _chat(messages: list[dict], *, temperature: float = 0.0, json_mode: bool = False, max_tokens: int = 1024) -> str:
    kwargs: dict[str, Any] = dict(
        model=get_settings().groq_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if _is_reasoning_model(kwargs["model"]):
        # Reasoning tokens count against max_tokens; keep reasoning short so the answer fits.
        kwargs["extra_body"] = {"reasoning_effort": "low"}
    try:
        resp = await get_client().chat.completions.create(**kwargs)
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"Groq request failed: {exc}") from exc
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        log.warning("Groq response hit max_tokens=%d and was cut off", max_tokens)
    return (choice.message.content or "").strip()


def _is_reasoning_model(model: str) -> bool:
    m = model.lower()
    return "gpt-oss" in m or "qwen3" in m


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError(f"Model did not return valid JSON: {text[:200]}")


def _format_context(chunks: list[str]) -> str:
    return "\n\n".join(f"[{i}] {c}" for i, c in enumerate(chunks, start=1))


async def generate_answer(question: str, chunks: list[str]) -> str:
    system = (
        "You answer questions using ONLY the numbered context passages. "
        "Do not use outside knowledge. Be concise and factual. "
        f'If the context does not contain the answer, reply exactly: "{REFUSAL}"'
    )
    user = f"Context:\n{_format_context(chunks)}\n\nQuestion: {question}\n\nAnswer:"
    return await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        max_tokens=700,
    )


async def judge_completeness(question: str, answer: str) -> tuple[float, str]:
    """Used when no reference answer is provided. Returns (score 0-1, reason)."""
    system = (
        "You grade how completely an answer addresses every part of a question. "
        "Ignore whether the facts are true; judge only coverage of what was asked. "
        'Return JSON: {"score": <float 0-1>, "missing_aspects": [<str>], "reason": <str>}'
    )
    user = f"Question: {question}\n\nAnswer: {answer}"
    data = _parse_json(
        await _chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_mode=True,
            max_tokens=400,
        )
    )
    try:
        score = float(data.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = min(max(score, 0.0), 1.0)
    reason = str(data.get("reason", ""))
    missing = data.get("missing_aspects") or []
    if missing:
        reason = f"{reason} Missing: {', '.join(map(str, missing))}".strip()
    return score, reason


async def suggest_fix(
    *,
    question: str,
    answer: str,
    chunks: list[str],
    scores: dict[str, float],
    failure_type: str,
    config: dict[str, Any],
    details: dict[str, Any],
) -> dict:
    system = (
        "You are a RAG pipeline debugging expert. Given an evaluation of one RAG query, "
        "explain the most likely root cause and give concrete, specific fixes "
        "(chunking, retrieval, top_k, embedding model, reranking, prompt, query rewriting, data quality). "
        "Prefer fixes that target the weakest score. Be brief.\n\n"
        "Reply in plain text using exactly these section headings:\n"
        "SUMMARY: <one sentence>\n"
        "ROOT CAUSE: <one or two sentences>\n"
        "ACTIONS:\n- <fix 1>\n- <fix 2>\n(up to 5)\n"
        "SUGGESTED CONFIG:\n- <parameter>: <new value>\n(only parameters you would change, or 'none')"
    )
    preview = _format_context([c[:400] for c in chunks])
    user = json.dumps(
        {
            "question": question,
            "generated_answer": answer,
            "scores_0_to_1": scores,
            "classified_failure_type": failure_type,
            "pipeline_config": config,
            "unsupported_claims": details.get("faithfulness", {}).get("unsupported_claims", []),
            "completeness_notes": details.get("completeness", {}).get("reason", ""),
            "retrieved_context_preview": preview,
        },
        ensure_ascii=False,
    )
    text = await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=2048,
    )
    if not text:
        raise LLMError("Empty fix suggestion from model")
    return parse_fix_text(text)


_SECTION = re.compile(
    r"^\s*[#*\s]*(summary|root\s*cause|actions|suggested\s*config)[*\s]*:[*\s]*(.*)$",
    re.I | re.M,
)
_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _coerce(value: str) -> Any:
    v = value.strip().strip("`\"'")
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    return v


def parse_fix_text(text: str) -> dict:
    """Parse the SUMMARY / ROOT CAUSE / ACTIONS / SUGGESTED CONFIG sections."""
    sections: dict[str, str] = {}
    matches = list(_SECTION.finditer(text))
    for i, m in enumerate(matches):
        key = re.sub(r"\s+", "_", m.group(1).lower())
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[key] = (m.group(2) + "\n" + text[m.end():end]).strip()

    if not sections:  # model ignored the format; keep its text rather than failing
        return {"summary": text.strip()[:1000], "root_cause": "", "actions": [], "suggested_config": {}}

    def items(block: str) -> list[str]:
        out = [_ITEM.sub("", l).strip() for l in block.splitlines()]
        return [l.strip("* ") for l in out if l and l.lower() not in {"none", "n/a"}]

    cfg: dict[str, Any] = {}
    for line in items(sections.get("suggested_config", "")):
        if ":" in line:
            k, v = line.split(":", 1)
        elif "=" in line:
            k, v = line.split("=", 1)
        else:
            continue
        k = k.strip().strip("`*").strip()
        if k:
            cfg[k] = _coerce(v)

    return {
        "summary": " ".join(sections.get("summary", "").split()),
        "root_cause": " ".join(sections.get("root_cause", "").split()),
        "actions": items(sections.get("actions", ""))[:5],
        "suggested_config": cfg,
    }
