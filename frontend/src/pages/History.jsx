import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { errorMessage, listDocuments, listEvaluations } from "../api/client";
import DocumentPicker from "../components/DocumentPicker";
import { FailureBadge } from "../components/results";
import { EmptyState, ErrorAlert, LoadingBlock, PageHeader } from "../components/ui";
import { SCORE_META, formatDate, humanize, passes } from "../lib/format";
import { setLastDoc } from "../lib/lastDoc";

function ScorePill({ k, value }) {
  const ok = passes(k, value);
  return (
    <span className={`inline-block w-12 rounded-md py-1 text-center text-xs font-semibold tabular-nums ${ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
      {(value ?? 0).toFixed(2)}
    </span>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div className="card p-5">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold tabular-nums text-navy-950">{value}</p>
      {sub && <p className="mt-1 truncate text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function History() {
  const { docId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");

  const load = () => {
    setError("");
    setData(null);
    listEvaluations(docId)
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
    listDocuments()
      .then((d) => setDoc(d.items.find((x) => x.id === docId) || null))
      .catch(() => {});
  };

  useEffect(() => {
    if (!docId) return;
    setLastDoc(docId);
    load();
  }, [docId]);

  const items = data?.items || [];
  const failureTypes = useMemo(() => [...new Set(items.map((e) => e.failure.failure_type))].sort(), [items]);
  const shown = items.filter(
    (e) => (!filter || e.failure.failure_type === filter) && (!query || e.question.toLowerCase().includes(query.toLowerCase()))
  );

  const stats = useMemo(() => {
    if (!items.length) return null;
    const avg = (k) => items.reduce((s, e) => s + (e.scores[k] ?? 0), 0) / items.length;
    const counts = items.reduce((m, e) => ((m[e.failure.failure_type] = (m[e.failure.failure_type] || 0) + 1), m), {});
    const [topFailure, topCount] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    return { avg, topFailure, topCount };
  }, [items]);

  if (!docId) {
    return (
      <div>
        <PageHeader title="Evaluation history" description="Pick a document to see its past evaluations." />
        <DocumentPicker linkTo={(d) => `/history/${d.id}`} actionLabel="History" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="History"
        title={doc?.filename || "Evaluation history"}
        description={data ? `${data.total} evaluation${data.total === 1 ? "" : "s"} for this document.` : null}
        actions={
          <>
            <Link to="/history" className="btn-secondary">
              Switch document
            </Link>
            <Link to={`/evaluate/${docId}`} className="btn-primary">
              New evaluation
            </Link>
          </>
        }
      />

      {error && <ErrorAlert message={error} onRetry={load} />}
      {!error && !data && <LoadingBlock label="Loading evaluations…" />}

      {data && items.length === 0 && (
        <EmptyState title="No evaluations yet" action={<Link to={`/evaluate/${docId}`} className="btn-primary">Ask a question</Link>}>
          Run your first evaluation to see scores and diagnoses here.
        </EmptyState>
      )}

      {stats && (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            {SCORE_META.map((m) => (
              <Stat key={m.key} label={`Avg ${m.label}`} value={stats.avg(m.key).toFixed(2)} sub={`Threshold ${m.threshold}`} />
            ))}
            <div className="col-span-2 lg:col-span-1">
              <Stat label="Most common failure" value={stats.topCount} sub={humanize(stats.topFailure)} />
            </div>
          </section>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <input
              type="search"
              className="input sm:max-w-xs"
              placeholder="Search questions…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select className="input sm:max-w-[240px]" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by failure type">
              <option value="">All failure types</option>
              {failureTypes.map((t) => (
                <option key={t} value={t}>
                  {humanize(t)}
                </option>
              ))}
            </select>
          </div>

          <div className="card mt-4 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-navy-950 text-left text-xs font-semibold uppercase tracking-wider text-navy-100">
                  <tr>
                    <th className="px-5 py-3">Question</th>
                    {SCORE_META.map((m) => (
                      <th key={m.key} className="whitespace-nowrap px-2 py-3 text-center" title={m.label}>
                        {m.label.split(" ")[0]}
                      </th>
                    ))}
                    <th className="px-5 py-3">Failure</th>
                    <th className="whitespace-nowrap px-5 py-3">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {shown.map((e) => {
                    const to = `/results/${docId}/${e.evaluation_id}`;
                    return (
                      <tr
                        key={e.evaluation_id}
                        className="cursor-pointer transition hover:bg-slate-50"
                        onClick={() => navigate(to, { state: { evaluation: e } })}
                      >
                        <td className="max-w-md px-5 py-4">
                          <Link
                            to={to}
                            state={{ evaluation: e }}
                            className="line-clamp-2 font-medium text-navy-950 hover:underline"
                            onClick={(ev) => ev.stopPropagation()}
                          >
                            {e.question}
                          </Link>
                        </td>
                        {SCORE_META.map((m) => (
                          <td key={m.key} className="px-2 py-4 text-center">
                            <ScorePill k={m.key} value={e.scores[m.key]} />
                          </td>
                        ))}
                        <td className="px-5 py-4">
                          <FailureBadge failure={e.failure} size="sm" />
                        </td>
                        <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-500">{formatDate(e.created_at)}</td>
                      </tr>
                    );
                  })}
                  {shown.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-5 py-10 text-center text-sm text-slate-500">
                        No evaluations match your filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          {data.total > items.length && (
            <p className="mt-3 text-xs text-slate-500">Showing the latest {items.length} of {data.total} evaluations.</p>
          )}
        </>
      )}
    </div>
  );
}
