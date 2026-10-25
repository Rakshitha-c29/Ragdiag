"""The four RAG quality scores, each in [0, 1].

context_relevance  highest cosine similarity (MiniLM) between the question and any retrieved chunk.
faithfulness       share of answer claims entailed by at least one retrieved chunk (DeBERTa NLI).
                   Markdown is stripped from claims and headings from chunk edges first. Answers
                   under 10 words are one claim, phrased with the question and checked against
                   each chunk and all chunks together.
completeness       with a reference answer: share of reference sentences entailed by the answer (NLI).
                   without one: Groq judges how fully the answer covers the question.
precision          rank-weighted average precision of the retrieved chunks, where a chunk is
                   relevant if it supports an answer claim or is close to the question.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings
from app.services import llm
from app.services.models import get_nli
from app.services.vector_store import Retrieved, embed

log = logging.getLogger(__name__)

_CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[A-Z0-9])|\n+")
_BULLET = re.compile(r"^\s*(?:[-*•+]|\d+[.)])\s+")

# Answers shorter than this are checked as a single claim, phrased with the question.
SHORT_ANSWER_WORDS = 10


# ---------- Markdown ----------

_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_MD_QUOTE = re.compile(r"^\s{0,3}>\s?", re.M)
_MD_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", re.M)
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_STRONG = re.compile(r"(\*\*|__|~~)(.+?)\1")
_MD_EM = re.compile(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])")
_MD_CODE = re.compile(r"`+([^`]*)`+")


def strip_markdown(text: str) -> str:
    text = _MD_TABLE_SEP.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_QUOTE.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    text = _MD_STRONG.sub(r"\2", text)
    text = _MD_EM.sub(r"\2", text)
    # table rows: "| a | b |" -> "a, b"
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("|") or line.count("|") >= 2:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            line = ", ".join(c for c in cells if c)
        lines.append(line)
    return "\n".join(lines).replace(" ", " ").replace("‑", "-")


def split_claims(text: str, min_words: int = 3) -> list[str]:
    text = strip_markdown(_CITATION.sub("", text))
    parts = (_BULLET.sub("", p).strip() for p in _SENT_SPLIT.split(text))
    return [p for p in parts if len(p.split()) >= min_words]


# ---------- Chunk clean-up for NLI ----------

_SMALL_WORDS = {"a", "an", "and", "the", "of", "for", "to", "in", "on", "or", "with", "at", "by", "&", "vs"}
_NUMBERED_HEADING = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.|[A-Z]\.)\s+\S")


def _is_heading(line: str) -> bool:
    """Short title-like line with no sentence punctuation, e.g. 'Customer Support' or '2.1 Warranty'."""
    s = strip_markdown(line).strip()
    if not s or len(s) > 80 or s[-1] in ".!?;,":
        return False
    words = s.rstrip(":").split()
    if not words or len(words) > 8:
        return False
    if _NUMBERED_HEADING.match(s) or line.lstrip().startswith("#"):
        return True
    content = [w for w in words if w.lower() not in _SMALL_WORDS]
    return bool(content) and all(not w[0].isalpha() or w[0].isupper() for w in content)


_SENT_END = re.compile(r"[.!?][\"')\]]?(?=\s|$)")
_LIST_MARK = re.compile(r"[•▪●◦]|(?:^|\s)[-*]\s")


def clean_premise(chunk: str) -> str:
    """Prepare a chunk as NLI premise. NLI stops predicting entailment, even for sentences
    copied word for word, when the premise contains stray headings (e.g. the next section's
    title glued to the end) or sentences the chunker cut in half. So:
      - drop standalone heading lines (at the edges and between paragraphs)
      - drop a half sentence at the start (chunk begins mid-sentence) and at the end
    Bulleted text is left alone, since list items often have no full stops."""
    lines = [l.strip() for l in chunk.splitlines() if l.strip() and not _is_heading(l)]
    text = " ".join(lines)
    if not text:
        return " ".join(chunk.split())

    ends = list(_SENT_END.finditer(text))
    if ends:
        # leading fragment: chunk starts mid-sentence (lowercase start)
        head = text[: ends[0].end()]
        if text[0].islower() and len(ends) > 1 and not _LIST_MARK.search(head):
            text = text[ends[0].end():].lstrip()
            ends = list(_SENT_END.finditer(text))
        # trailing fragment: text after the last full stop
        tail = text[ends[-1].end():] if ends else ""
        if tail.strip() and not _LIST_MARK.search(tail):
            text = text[: ends[-1].end()]
    return text


# ---------- Refusals ----------

_REFUSAL_PATTERNS = [
    re.compile(p)
    for p in (
        r"^i (?:don't|do not) know\b",
        r"^i (?:cannot|can ?not|can't|could not|couldn't) find\b",
        r"^(?:the )?(?:provided |given |retrieved )?(?:context|passages?|documents?) (?:does|do|did)(?: not|n't)\b",
        r"^based on the (?:provided |given )?context,? i (?:don't|do not|cannot|can't) (?:know|find|answer|determine)\b",
        r"^there is no (?:information|mention)\b.*\b(?:context|passages?|documents?)\b",
    )
]


def is_refusal(answer: str) -> bool:
    """True when the answer declines to answer from the context. Only the opening sentence is
    checked, and answers that go on to answer anyway ("...does not say X, but Y") don't count."""
    text = strip_markdown(answer).strip().lower().replace("’", "'")
    if not text:
        return False
    if text.rstrip(".").startswith(llm.REFUSAL.lower().rstrip(".")):
        return True
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if re.search(r"\b(?:but|however|although)\b", first) or len(text.split()) > 40:
        return False
    return any(p.search(first) for p in _REFUSAL_PATTERNS)


def _nli_sync(premises: list[str], hypotheses: list[str], batch_size: int = 16) -> tuple[np.ndarray, np.ndarray]:
    """Entailment and contradiction probabilities for each (premise, hypothesis) pair."""
    import torch

    tok, model, idx = get_nli()
    ent, con = [], []
    for start in range(0, len(premises), batch_size):
        enc = tok(
            premises[start : start + batch_size],
            hypotheses[start : start + batch_size],
            truncation="only_first",
            max_length=512,
            padding=True,
            return_tensors="pt",
        ).to(model.device)
        with torch.inference_mode():
            probs = torch.softmax(model(**enc).logits, dim=-1).cpu().numpy()
        ent.append(probs[:, idx["entailment"]])
        con.append(probs[:, idx["contradiction"]] if "contradiction" in idx else np.zeros(len(probs)))
    return np.concatenate(ent), np.concatenate(con)


async def nli(premises: list[str], hypotheses: list[str]):
    if not premises:
        return np.zeros(0), np.zeros(0)
    return await asyncio.to_thread(_nli_sync, premises, hypotheses)


@dataclass
class ScoreResult:
    context_relevance: float
    faithfulness: float
    completeness: float
    precision: float
    chunk_supports: list[bool]
    chunk_relevant: list[bool]
    details: dict = field(default_factory=dict)

    @property
    def overall(self) -> float:
        return round(
            (self.context_relevance + self.faithfulness + self.completeness + self.precision) / 4, 4
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "context_relevance": self.context_relevance,
            "faithfulness": self.faithfulness,
            "completeness": self.completeness,
            "precision": self.precision,
            "overall": self.overall,
        }


def _r(x: float) -> float:
    return round(float(x), 4)


async def score_all(
    question: str, answer: str, chunks: list[Retrieved], reference: str | None
) -> ScoreResult:
    s = get_settings()
    thr = s.nli_entail_threshold
    texts = [c.text for c in chunks]
    sims = np.clip(np.array([c.similarity for c in chunks], dtype=float), 0.0, 1.0)
    refused = is_refusal(answer)
    details: dict = {"answer_refused": refused}

    # --- Context relevance: the best-matching chunk ---
    context_relevance = float(sims.max()) if len(sims) else 0.0
    details["context_relevance"] = {"method": "max", "per_chunk_similarity": [_r(x) for x in sims]}

    # --- Faithfulness ---
    clean_answer = " ".join(strip_markdown(_CITATION.sub("", answer)).split())
    premises = [clean_premise(t) for t in texts]
    chunk_supports = [False] * len(texts)
    hypotheses: list[str] = []  # what NLI checks, one per claim
    short = False

    if refused:
        claims = []
    elif 0 < len(clean_answer.split()) < SHORT_ANSWER_WORDS and len(split_claims(answer, min_words=1)) <= 1:
        # One short sentence. "30 days." alone is not a statement, so phrase it with the question.
        # (Several short sentences, e.g. "Returns: 30 days. Warranty: 2 years.", may each come
        # from a different chunk, so those are checked one by one below.)
        short = True
        claims = [clean_answer]
        hypotheses = [f'The answer to "{question.strip().rstrip("?")}" is {clean_answer}']
    else:
        claims = split_claims(answer)
        hypotheses = claims

    if refused:
        faithfulness = 1.0  # declining to answer is not a hallucination
        details["faithfulness"] = {"claims": [], "unsupported_claims": [], "note": "answer refused"}
    elif not claims:
        faithfulness = 0.0
        details["faithfulness"] = {"claims": [], "unsupported_claims": [], "note": "no checkable claims"}
    else:
        # Each claim is checked against every chunk; a short answer also against all chunks together.
        cols = premises + ([" ".join(premises)] if short and len(premises) > 1 else [])
        prem = [p for _ in hypotheses for p in cols]
        hyp = [h for h in hypotheses for _ in cols]
        ent, con = await nli(prem, hyp)
        ent = ent.reshape(len(claims), len(cols))
        con = con.reshape(len(claims), len(cols))
        per_chunk = ent[:, : len(premises)]
        best = ent.max(axis=1)
        supported = best >= thr
        faithfulness = float(supported.mean())
        chunk_supports = (per_chunk >= thr).any(axis=0).tolist()
        details["faithfulness"] = {
            "mean_entailment": _r(best.mean()),
            "method": "short_answer" if short else "per_claim",
            "claims": [
                {
                    "claim": c,
                    "entailment": _r(best[i]),
                    "supported": bool(supported[i]),
                    "best_chunk_rank": int(per_chunk[i].argmax()) + 1,
                    "contradicted": bool(con[i].max() >= thr),
                }
                for i, c in enumerate(claims)
            ],
            "unsupported_claims": [c for i, c in enumerate(claims) if not supported[i]],
        }

    # --- Completeness ---
    if refused:
        completeness = 0.0
        details["completeness"] = {"method": "refusal", "reason": "Model declined to answer."}
    elif reference:
        ref_sents = split_claims(reference, min_words=2) or [reference.strip()]
        ent, _ = await nli([clean_answer or answer] * len(ref_sents), ref_sents)
        covered = ent >= thr
        completeness = float(covered.mean())
        details["completeness"] = {
            "method": "nli_vs_reference",
            "missing_reference_points": [r for i, r in enumerate(ref_sents) if not covered[i]],
            "reason": f"{int(covered.sum())}/{len(ref_sents)} reference points covered.",
        }
    else:
        try:
            completeness, reason = await llm.judge_completeness(question, answer)
            details["completeness"] = {"method": "llm_judge", "reason": reason}
        except llm.LLMError as exc:
            log.warning("Completeness judge failed, using embedding fallback: %s", exc)
            q, a = await asyncio.to_thread(embed, [question, answer])
            completeness = float(np.clip(q @ a, 0.0, 1.0))
            details["completeness"] = {"method": "embedding_fallback", "reason": str(exc)}

    # --- Precision (rank-aware) ---
    relevant = [bool(sup or sim >= s.chunk_relevance_threshold) for sup, sim in zip(chunk_supports, sims)]
    hits, ap_sum = 0, 0.0
    for k, rel in enumerate(relevant, start=1):
        if rel:
            hits += 1
            ap_sum += hits / k
    precision = ap_sum / hits if hits else 0.0
    details["precision"] = {
        "relevant_chunks": hits,
        "retrieved_chunks": len(relevant),
        "precision_at_k": _r(hits / len(relevant)) if relevant else 0.0,
    }

    return ScoreResult(
        context_relevance=_r(context_relevance),
        faithfulness=_r(faithfulness),
        completeness=_r(completeness),
        precision=_r(precision),
        chunk_supports=chunk_supports,
        chunk_relevant=relevant,
        details=details,
    )
