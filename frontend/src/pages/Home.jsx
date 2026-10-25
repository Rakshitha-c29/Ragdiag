import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage, uploadPdf } from "../api/client";
import DocumentPicker from "../components/DocumentPicker";
import { ErrorAlert, PageHeader, Spinner } from "../components/ui";
import { formatBytes } from "../lib/format";
import { setLastDoc } from "../lib/lastDoc";

const REDIRECT_SECONDS = 3;

export default function Home() {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [countdown, setCountdown] = useState(REDIRECT_SECONDS);

  // Auto-navigate to Evaluate after a successful upload.
  useEffect(() => {
    if (!result || countdown === null) return; // null = redirect cancelled
    if (countdown <= 0) {
      navigate(`/evaluate/${result.id}`);
      return;
    }
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [result, countdown, navigate]);

  const handleFile = async (f) => {
    setError("");
    setResult(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf") && f.type !== "application/pdf") {
      setError("Please choose a PDF file.");
      return;
    }
    setFile(f);
    setUploading(true);
    setProgress(0);
    try {
      const doc = await uploadPdf(f, setProgress);
      setLastDoc(doc.id);
      setCountdown(REDIRECT_SECONDS);
      setResult(doc);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (!uploading) handleFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div>
      <PageHeader
        eyebrow="Step 1"
        title="Upload a document"
        description="Upload a PDF to build its retrieval index. Then ask questions to see how well your RAG pipeline answers them, and why it fails when it does."
      />

      <div className="grid gap-8 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <div
            role="button"
            tabIndex={0}
            onClick={() => !uploading && inputRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !uploading && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex min-h-[280px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-400 ${
              dragging
                ? "border-navy-500 bg-navy-50"
                : "border-slate-300 bg-white hover:border-navy-400 hover:bg-slate-50"
            } ${uploading ? "cursor-wait" : ""}`}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={(e) => {
                handleFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            {uploading ? (
              <div className="w-full max-w-xs">
                <Spinner className="mx-auto h-8 w-8 text-navy-700" />
                <p className="mt-4 truncate text-sm font-medium text-navy-950">Uploading {file?.name}</p>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-navy-700 transition-all" style={{ width: `${progress}%` }} />
                </div>
                <p className="mt-2 text-xs tabular-nums text-slate-500">
                  {progress < 100 ? `${progress}%` : "Checking PDF…"}
                </p>
              </div>
            ) : (
              <>
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-navy-900 text-white shadow">
                  <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
                  </svg>
                </div>
                <p className="mt-5 text-base font-semibold text-navy-950">
                  {dragging ? "Drop to upload" : "Drag and drop a PDF here"}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  or <span className="font-semibold text-navy-700 underline underline-offset-2">browse files</span>
                </p>
                <p className="mt-4 text-xs text-slate-400">PDF only · text-based (scanned PDFs need OCR first)</p>
              </>
            )}
          </div>

          <ErrorAlert message={error} />

          {result && (
            <div className="card border-emerald-200 p-5">
              <div className="flex items-start gap-3">
                <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.58l7.3-7.3a1 1 0 0 1 1.4 0Z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-navy-950">
                    {result.duplicate ? "Already uploaded — using the existing document" : "Upload complete"}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-slate-500">
                    {result.filename} · {result.num_pages} pages · {formatBytes(result.size_bytes)}
                  </p>
                  <div className="mt-3 flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-500">doc_id</span>
                    <code className="truncate rounded bg-navy-50 px-2 py-1 font-mono text-xs text-navy-900 ring-1 ring-inset ring-navy-200">
                      {result.id}
                    </code>
                    <button
                      className="text-xs font-medium text-navy-700 hover:text-navy-900"
                      onClick={() => navigator.clipboard?.writeText(result.id)}
                    >
                      Copy
                    </button>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button className="btn-primary" onClick={() => navigate(`/evaluate/${result.id}`)}>
                      Evaluate now
                    </button>
                    {countdown !== null && (
                      <>
                        <button className="btn-secondary" onClick={() => setCountdown(null)}>
                          Stay here
                        </button>
                        <span className="text-xs text-slate-500">Opening Evaluate in {countdown}s…</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          <p className="section-title mb-3">Recent documents</p>
          <DocumentPicker linkTo={(d) => `/evaluate/${d.id}`} actionLabel="Evaluate" limit={6} />
        </div>
      </div>
    </div>
  );
}
