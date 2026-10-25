import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage, listDocuments } from "../api/client";
import { formatBytes, formatDate } from "../lib/format";
import { EmptyState, ErrorAlert, LoadingBlock } from "./ui";

/** List of uploaded documents; each row links to `linkTo(doc)`. */
export default function DocumentPicker({ linkTo, actionLabel = "Open", limit }) {
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    listDocuments()
      .then((d) => setDocs(d.items))
      .catch((e) => setError(errorMessage(e)));
  };
  useEffect(load, []);

  if (error) return <ErrorAlert message={error} onRetry={load} />;
  if (!docs) return <LoadingBlock label="Loading documents…" />;
  if (docs.length === 0)
    return (
      <EmptyState title="No documents yet" action={<Link to="/" className="btn-primary">Upload a PDF</Link>}>
        Upload a PDF to start evaluating your RAG pipeline.
      </EmptyState>
    );

  const shown = limit ? docs.slice(0, limit) : docs;
  return (
    <ul className="card divide-y divide-slate-100 overflow-hidden">
      {shown.map((d) => (
        <li key={d.id}>
          <Link to={linkTo(d)} className="group flex items-center gap-4 px-5 py-4 transition hover:bg-slate-50">
            <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg bg-navy-50 text-[11px] font-bold text-navy-700 ring-1 ring-inset ring-navy-100">
              PDF
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-navy-950">{d.filename}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {d.num_pages} page{d.num_pages === 1 ? "" : "s"} · {formatBytes(d.size_bytes)} · {d.evaluation_count}{" "}
                evaluation{d.evaluation_count === 1 ? "" : "s"} · {formatDate(d.uploaded_at)}
              </p>
            </div>
            <span className="text-sm font-medium text-navy-700 opacity-70 transition group-hover:opacity-100">
              {actionLabel} →
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
