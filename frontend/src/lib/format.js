export const SCORE_META = [
  {
    key: "context_relevance",
    label: "Context Relevance",
    threshold: 0.35, // keep in sync with THRESHOLD_* in backend/app/config.py
    help: "How closely the best retrieved chunk matches the question.",
  },
  {
    key: "faithfulness",
    label: "Faithfulness",
    threshold: 0.6,
    help: "Share of answer claims backed by the retrieved chunks.",
  },
  {
    key: "completeness",
    label: "Completeness",
    threshold: 0.5,
    help: "How fully the answer covers what was asked.",
  },
  {
    key: "precision",
    label: "Precision",
    threshold: 0.4,
    help: "How many retrieved chunks were useful, weighted by rank.",
  },
];

export const passes = (key, value) => {
  const meta = SCORE_META.find((m) => m.key === key);
  return value >= (meta?.threshold ?? 0.5);
};

export const pct = (v, digits = 0) => `${((v ?? 0) * 100).toFixed(digits)}%`;

const ACRONYMS = { llm: "LLM", rag: "RAG", nli: "NLI" };

export const humanize = (s = "") =>
  s
    .split("_")
    .map((w) => ACRONYMS[w.toLowerCase()] || w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

export const formatDate = (iso) => {
  if (!iso) return "";
  // Backend may omit the timezone; treat naive timestamps as UTC.
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

export const formatBytes = (n) => {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

export const FAILURE_STYLES = {
  no_failure: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  bad_retrieval: "bg-amber-50 text-amber-800 ring-amber-600/20",
  hallucination_in_context: "bg-red-50 text-red-800 ring-red-600/20",
  llm_ignored_context: "bg-orange-50 text-orange-800 ring-orange-600/20",
  incomplete_answer: "bg-sky-50 text-sky-800 ring-sky-600/20",
};

export const FAILURE_DESCRIPTIONS = {
  no_failure: "The pipeline answered well on every dimension.",
  bad_retrieval: "The retriever did not surface the chunks needed to answer.",
  hallucination_in_context: "The answer states things the retrieved context does not support.",
  llm_ignored_context: "Relevant context was retrieved but the model did not use it.",
  incomplete_answer: "The answer misses parts of what the question asked.",
};
