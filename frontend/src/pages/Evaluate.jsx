import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { errorMessage, evaluate, listDocuments } from "../api/client";
import DocumentPicker from "../components/DocumentPicker";
import { ErrorAlert, PageHeader, Spinner } from "../components/ui";
import { setLastDoc } from "../lib/lastDoc";

const EXAMPLES = ["What is the main conclusion of this document?", "Summarise the key requirements.", "What are the limitations mentioned?"];

function useDocument(docId) {
  const [doc, setDoc] = useState(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    if (!docId) return;
    setDoc(null);
    setMissing(false);
    listDocuments()
      .then((d) => {
        const found = d.items.find((x) => x.id === docId);
        found ? setDoc(found) : setMissing(true);
      })
      .catch(() => {}); // the header just falls back to the id
  }, [docId]);
  return { doc, missing };
}

function Elapsed({ since }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const s = Math.floor((now - since) / 1000);
  return <span className="tabular-nums">{Math.floor(s / 60)}:{String(s % 60).padStart(2, "0")}</span>;
}

export default function Evaluate() {
  const { docId } = useParams();
  const navigate = useNavigate();
  const { doc, missing } = useDocument(docId);

  const [question, setQuestion] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [reference, setReference] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [error, setError] = useState("");
  const abortRef = useRef(null);

  useEffect(() => {
    if (docId) setLastDoc(docId);
  }, [docId]);
  useEffect(() => () => abortRef.current?.abort(), []);

  if (!docId) {
    return (
      <div>
        <PageHeader eyebrow="Step 2" title="Choose a document" description="Pick the document you want to ask questions about." />
        <DocumentPicker linkTo={(d) => `/evaluate/${d.id}`} actionLabel="Evaluate" />
      </div>
    );
  }

  const submit = async (e) => {
    e.preventDefault();
    if (question.trim().length < 3 || loading) return;
    setError("");
    setLoading(true);
    setStartedAt(Date.now());
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const payload = { doc_id: docId, question: question.trim(), top_k: Number(topK) || undefined };
      if (reference.trim()) payload.reference_answer = reference.trim();
      const result = await evaluate(payload, controller.signal);
      navigate(`/results/${docId}/${result.evaluation_id}`, { state: { evaluation: result } });
    } catch (err) {
      if (!controller.signal.aborted) setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Step 2 · Evaluate"
        title="Ask a question"
        description={
          doc ? (
            <>
              Evaluating against <span className="font-semibold text-navy-900">{doc.filename}</span> ({doc.num_pages} page{doc.num_pages === 1 ? "" : "s"}).
            </>
          ) : (
            <>
              Document <code className="font-mono text-xs">{docId}</code>
            </>
          )
        }
        actions={
          <Link to={`/history/${docId}`} className="btn-secondary">
            View history
          </Link>
        }
      />

      {missing && (
        <div className="mb-6">
          <ErrorAlert message="This document no longer exists. Upload it again or pick another one." />
        </div>
      )}

      <form onSubmit={submit} className="card p-6 sm:p-8">
        <label htmlFor="question" className="label">
          Question
        </label>
        <textarea
          id="question"
          rows={4}
          className="input resize-y text-base"
          placeholder="e.g. What is the refund window for online orders?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === "Enter" && submit(e)}
          disabled={loading}
          maxLength={2000}
          autoFocus
        />
        {!question && !loading && (
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => setQuestion(q)}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600 transition hover:border-navy-300 hover:text-navy-900"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="mt-6 text-sm font-medium text-navy-700 hover:text-navy-900"
          aria-expanded={showAdvanced}
        >
          {showAdvanced ? "− Hide" : "+ Show"} advanced options
        </button>

        {showAdvanced && (
          <div className="mt-4 grid gap-5 rounded-lg bg-slate-50 p-5 ring-1 ring-inset ring-slate-200 sm:grid-cols-4">
            <div className="sm:col-span-3">
              <label htmlFor="reference" className="label">
                Reference answer <span className="font-normal text-slate-500">(optional)</span>
              </label>
              <textarea
                id="reference"
                rows={3}
                className="input"
                placeholder="The ideal answer. Completeness is then measured against it."
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                disabled={loading}
              />
            </div>
            <div>
              <label htmlFor="topk" className="label">
                Top K chunks
              </label>
              <input
                id="topk"
                type="number"
                min={1}
                max={20}
                className="input"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>
        )}

        <div className="mt-6">
          <ErrorAlert message={error} />
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-6">
          <p className="text-xs text-slate-500">Ctrl + Enter to submit</p>
          <div className="flex gap-2">
            {loading && (
              <button type="button" className="btn-secondary" onClick={() => abortRef.current?.abort()}>
                Cancel
              </button>
            )}
            <button type="submit" className="btn-primary min-w-[140px]" disabled={loading || question.trim().length < 3}>
              {loading ? (
                <>
                  <Spinner className="h-4 w-4" /> Evaluating…
                </>
              ) : (
                "Run evaluation"
              )}
            </button>
          </div>
        </div>
      </form>

      {loading && (
        <div className="card mt-6 flex items-center gap-5 p-6" aria-live="polite">
          <Spinner className="h-10 w-10 flex-none text-navy-800" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-navy-950">
              Running the pipeline · <Elapsed since={startedAt} />
            </p>
            <p className="mt-1 text-sm text-slate-600">
              Retrieving chunks, generating an answer, scoring it and diagnosing failures.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              The first run for a document builds its index and may download models, so it can take a few minutes.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
