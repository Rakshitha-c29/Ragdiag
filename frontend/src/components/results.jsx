import { useMemo, useState } from "react";
import { FAILURE_DESCRIPTIONS, FAILURE_STYLES, humanize, pct } from "../lib/format";

/* ---------- Score card ---------- */

export function ScoreCard({ label, value, threshold, help }) {
  const ok = value >= threshold;
  return (
    <div className={`card relative overflow-hidden p-5 ${ok ? "" : "border-red-200"}`}>
      <div className={`absolute inset-x-0 top-0 h-1 ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-navy-900">{label}</p>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
            ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
          }`}
        >
          {ok ? "Pass" : "Fail"}
        </span>
      </div>
      <p className={`mt-3 text-3xl font-bold tabular-nums ${ok ? "text-emerald-600" : "text-red-600"}`}>
        {(value ?? 0).toFixed(2)}
      </p>
      <div className="relative mt-3 h-1.5 w-full rounded-full bg-slate-100" aria-hidden="true">
        <div
          className={`h-full rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`}
          style={{ width: pct(Math.min(Math.max(value ?? 0, 0), 1)) }}
        />
        <div
          className="absolute -top-1 h-3.5 w-0.5 rounded bg-navy-900"
          style={{ left: pct(threshold) }}
          title={`Threshold ${threshold}`}
        />
      </div>
      <p className="mt-2 text-xs text-slate-500">Threshold {threshold.toFixed(2)}</p>
      {help && <p className="mt-1 text-xs text-slate-500">{help}</p>}
    </div>
  );
}

/* ---------- Failure badge ---------- */

export function FailureBadge({ failure, size = "md" }) {
  if (!failure) return null;
  const style = FAILURE_STYLES[failure.failure_type] || "bg-slate-100 text-slate-700 ring-slate-500/20";
  const pad = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";
  return (
    <span className={`inline-flex items-center gap-2 whitespace-nowrap rounded-full font-semibold ring-1 ring-inset ${style} ${pad}`}>
      {humanize(failure.failure_type)}
      <span className="font-medium opacity-75">{pct(failure.confidence)}</span>
    </span>
  );
}

export function FailureCard({ failure }) {
  const probs = Object.entries(failure.probabilities || {}).sort((a, b) => b[1] - a[1]);
  return (
    <div className="card p-6">
      <p className="section-title">Failure type</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <FailureBadge failure={failure} />
        {failure.source === "heuristic" && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600" title="Classifier model unavailable; rule-based result">
            rule-based
          </span>
        )}
        {failure.source === "thresholds" && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600" title="All four scores passed their thresholds">
            all scores passed
          </span>
        )}
      </div>
      <p className="mt-3 text-sm text-slate-600">
        {FAILURE_DESCRIPTIONS[failure.failure_type] || "Classified by the failure model."}
      </p>
      {probs.length > 1 && (
        <>
        {failure.source === "thresholds" && (
          <p className="mt-5 text-xs font-medium text-slate-500">Classifier model's prediction</p>
        )}
        <dl className={`${failure.source === "thresholds" ? "mt-2" : "mt-5"} space-y-2`}>
          {probs.map(([label, p]) => (
            <div key={label} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-xs">
              <dt className="truncate text-slate-600">{humanize(label)}</dt>
              <dd className="tabular-nums text-slate-500">{pct(p, 1)}</dd>
              <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-navy-700" style={{ width: pct(p, 1) }} />
              </div>
            </div>
          ))}
        </dl>
        </>
      )}
    </div>
  );
}

/* ---------- Fix suggestion ---------- */

export function FixSuggestionCard({ fix }) {
  if (!fix) return null;
  const config = Object.entries(fix.suggested_config || {});
  return (
    <div className="card overflow-hidden">
      <div className="border-b border-navy-800 bg-navy-900 px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-navy-200">Suggested fix</p>
        <p className="mt-1 text-base font-semibold text-white">{fix.summary || "No summary provided."}</p>
      </div>
      <div className="space-y-6 p-6">
        {fix.root_cause && (
          <div>
            <p className="section-title">Root cause</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">{fix.root_cause}</p>
          </div>
        )}
        {fix.actions?.length > 0 && (
          <div>
            <p className="section-title">Actions</p>
            <ol className="mt-3 space-y-3">
              {fix.actions.map((a, i) => (
                <li key={i} className="flex gap-3 text-sm text-slate-700">
                  <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-navy-100 text-xs font-bold text-navy-900">
                    {i + 1}
                  </span>
                  <span className="pt-0.5 leading-relaxed">{a}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {config.length > 0 && (
          <div>
            <p className="section-title">Suggested config</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {config.map(([k, v]) => (
                <code key={k} className="rounded-md bg-navy-50 px-2 py-1 text-xs text-navy-900 ring-1 ring-inset ring-navy-200">
                  {k} = {String(v)}
                </code>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Answer with unsupported claims highlighted ---------- */

const norm = (s) => s.replace(/\s+/g, " ").trim();

/** Locate each claim in the answer. Claims were split and lightly cleaned on the
 *  server (citations and bullets removed), so fall back to a prefix match. */
function findRanges(answer, claims) {
  const ranges = [];
  const lower = answer.toLowerCase();
  const missing = [];
  for (const claim of claims) {
    const c = norm(claim).toLowerCase();
    let start = lower.indexOf(c);
    let len = c.length;
    if (start < 0) {
      const head = c.slice(0, Math.min(40, c.length));
      start = lower.indexOf(head);
      if (start >= 0) {
        // extend to the end of the sentence
        const rest = answer.slice(start);
        const m = rest.match(/^[\s\S]*?[.!?](?=\s|$)/);
        len = m ? m[0].length : rest.length;
      }
    }
    if (start >= 0) ranges.push([start, start + len]);
    else missing.push(claim);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([...r]);
  }
  return { ranges: merged, missing };
}

export function HighlightedAnswer({ answer, unsupported = [], refused }) {
  const { ranges, missing } = useMemo(() => findRanges(answer || "", unsupported), [answer, unsupported]);

  const parts = [];
  let pos = 0;
  ranges.forEach(([s, e], i) => {
    if (s > pos) parts.push(<span key={`t${i}`}>{answer.slice(pos, s)}</span>);
    parts.push(
      <mark
        key={`m${i}`}
        className="rounded bg-red-100 px-0.5 text-red-800 decoration-red-400 decoration-2 underline-offset-4 [text-decoration-line:underline] [text-decoration-style:wavy]"
        title="Not supported by the retrieved context"
      >
        {answer.slice(s, e)}
      </mark>
    );
    pos = e;
  });
  if (pos < (answer || "").length) parts.push(<span key="end">{answer.slice(pos)}</span>);

  return (
    <div className="card p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="section-title">Generated answer</p>
        {unsupported.length > 0 ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-red-700">
            <span className="h-2.5 w-2.5 rounded-sm bg-red-200 ring-1 ring-red-400" />
            {unsupported.length} unsupported claim{unsupported.length > 1 ? "s" : ""}
          </span>
        ) : (
          !refused && <span className="text-xs text-emerald-700">All claims supported</span>
        )}
      </div>
      {refused && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
          The model declined to answer from the retrieved context.
        </p>
      )}
      <p className="mt-4 whitespace-pre-wrap text-[15px] leading-7 text-slate-800">{parts}</p>
      {missing.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="text-xs font-medium text-slate-500">Other unsupported claims</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-700">
            {missing.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ---------- Retrieved chunks accordion ---------- */

function Chevron({ open }) {
  return (
    <svg className={`h-4 w-4 flex-none text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z" clipRule="evenodd" />
    </svg>
  );
}

function Tag({ on, children }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${on ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
      {children}
    </span>
  );
}

export function ChunksAccordion({ chunks = [] }) {
  const [open, setOpen] = useState(() => new Set());
  const toggle = (i) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  const allOpen = open.size === chunks.length && chunks.length > 0;

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <p className="section-title">Retrieved chunks ({chunks.length})</p>
        {chunks.length > 0 && (
          <button
            className="text-xs font-medium text-navy-700 hover:text-navy-900"
            onClick={() => setOpen(allOpen ? new Set() : new Set(chunks.map((_, i) => i)))}
          >
            {allOpen ? "Collapse all" : "Expand all"}
          </button>
        )}
      </div>
      <ul className="divide-y divide-slate-100">
        {chunks.map((c, i) => {
          const isOpen = open.has(i);
          return (
            <li key={c.chunk_id || i}>
              <button
                className="flex w-full items-center gap-4 px-6 py-4 text-left transition hover:bg-slate-50"
                onClick={() => toggle(i)}
                aria-expanded={isOpen}
              >
                <span className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-navy-900 text-xs font-bold text-white">
                  {c.rank}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                    {c.page != null && <span>Page {c.page}</span>}
                    <span className="tabular-nums">Similarity {c.similarity.toFixed(3)}</span>
                    <Tag on={c.supports_answer}>{c.supports_answer ? "Supports answer" : "Not used"}</Tag>
                    <Tag on={c.relevant}>{c.relevant ? "Relevant" : "Not relevant"}</Tag>
                  </div>
                  {!isOpen && <p className="mt-1 truncate text-sm text-slate-700">{c.text}</p>}
                </div>
                <div className="hidden w-24 flex-none sm:block" aria-hidden="true">
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-navy-600" style={{ width: pct(Math.max(0, c.similarity)) }} />
                  </div>
                </div>
                <Chevron open={isOpen} />
              </button>
              {isOpen && (
                <div className="px-6 pb-5 pl-[4.25rem]">
                  <p className="whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 ring-1 ring-inset ring-slate-200">
                    {c.text}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
