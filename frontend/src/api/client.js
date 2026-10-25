import axios from "axios";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: API_URL });

/** Turn FastAPI / network errors into a readable message. */
export function errorMessage(err) {
  if (axios.isCancel(err)) return "Request cancelled.";
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join(".") || "input"}: ${d.msg}`).join("; ");
  }
  if (err?.code === "ERR_NETWORK") return `Cannot reach the API at ${API_URL}. Is the backend running?`;
  if (err?.response?.status) return `Request failed (${err.response.status}).`;
  return err?.message || "Something went wrong.";
}

export async function uploadPdf(file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/upload-pdf", form, {
    onUploadProgress: (e) => e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)),
  });
  return data;
}

export async function evaluate(payload, signal) {
  // No timeout: the first run downloads models and can take minutes.
  const { data } = await api.post("/evaluate", payload, { signal });
  return data;
}

export async function listDocuments(params = {}) {
  const { data } = await api.get("/documents", { params: { limit: 200, ...params } });
  return data;
}

export async function listEvaluations(docId, params = {}) {
  const { data } = await api.get(`/evaluations/${docId}`, { params: { limit: 200, ...params } });
  return data;
}

export async function getEvaluation(docId, evaluationId) {
  const data = await listEvaluations(docId);
  const found = data.items.find((e) => e.evaluation_id === evaluationId);
  if (!found) {
    const err = new Error("Evaluation not found.");
    err.response = { status: 404, data: { detail: "Evaluation not found." } };
    throw err;
  }
  return found;
}

export async function getHealth() {
  const { data } = await api.get("/health", { validateStatus: () => true });
  return data;
}
