import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { errorMessage, getEvaluation } from "../api/client";
import { ChunksAccordion, FailureCard, FixSuggestionCard, HighlightedAnswer, ScoreCard } from "../components/results";
import { ErrorAlert, LoadingBlock, PageHeader } from "../components/ui";
import { SCORE_META, formatDate } from "../lib/format";
import { setLastDoc } from "../lib/lastDoc";

export default function Results() {
  const { docId, evalId } = useParams();
  const { state } = useLocation();
  const fromNav = state?.evaluation?.evaluation_id === evalId ? state.evaluation : null;
  const [ev, setEv] = useState(fromNav);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    getEvaluation(docId, evalId)
      .then(setEv)
      .catch((e) => setError(errorMessage(e)));
  };

  useEffect(() => {
    setLastDoc(docId);
    if (!fromNav) load();
    else setEv(fromNav);
  }, [docId, evalId]);

  if (error)
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <ErrorAlert message={error} onRetry={load} />
        <Link to={`/history/${docId}`} className="btn-secondary">
          Back to history
        </Link>
      </div>
    );
  if (!ev) return <LoadingBlock label="Loading evaluation…" />;

  const unsupported = ev.score_details?.faithfulness?.unsupported_claims || [];
  const refused = !!ev.score_details?.answer_refused;
  const passed = SCORE_META.filter((m) => ev.scores[m.key] >= m.threshold).length;
  const completenessNote = ev.score_details?.completeness?.reason;

  return (
    <div>
      <PageHeader
        eyebrow={`Evaluation result · ${formatDate(ev.created_at)}`}
        title={ev.question}
        description={
          <>
            {passed} of 4 checks passed · overall {(ev.scores.overall ?? 0).toFixed(2)} · {(ev.latency_ms / 1000).toFixed(1)}s ·
            top-{ev.config?.top_k} of {ev.config?.total_chunks ?? "?"} chunks
          </>
        }
        actions={
          <>
            <Link to={`/history/${docId}`} className="btn-secondary">
              History
            </Link>
            <Link to={`/evaluate/${docId}`} className="btn-primary">
              Ask another question
            </Link>
          </>
        }
      />

      <section aria-label="Scores" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SCORE_META.map((m) => (
          <ScoreCard key={m.key} label={m.label} value={ev.scores[m.key]} threshold={m.threshold} help={m.help} />
        ))}
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <HighlightedAnswer answer={ev.generated_answer} unsupported={unsupported} refused={refused} />
          {ev.reference_answer && (
            <div className="card p-6">
              <p className="section-title">Reference answer</p>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{ev.reference_answer}</p>
              {completenessNote && <p className="mt-3 text-xs text-slate-500">{completenessNote}</p>}
            </div>
          )}
        </div>
        <div className="space-y-6">
          <FailureCard failure={ev.failure} />
          {!ev.reference_answer && completenessNote && (
            <div className="card p-6">
              <p className="section-title">Completeness notes</p>
              <p className="mt-2 text-sm text-slate-600">{completenessNote}</p>
            </div>
          )}
        </div>
      </div>

      <div className="mt-6">
        <FixSuggestionCard fix={ev.fix_suggestion} />
      </div>

      <div className="mt-6">
        <ChunksAccordion chunks={ev.retrieved_chunks} />
      </div>
    </div>
  );
}
