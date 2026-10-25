# RAGDiag frontend

React 18 + Vite + Tailwind CSS + React Router + axios.

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The backend must be running at http://localhost:8000. To point at another URL, copy `.env.example` to `.env` and set `VITE_API_URL`.

`npm run build` writes a static build to `dist/`.

## Pages

| Route | Page |
|---|---|
| `/` | Upload a PDF (drag and drop). Shows the `doc_id`, then opens Evaluate. Also lists recent documents. |
| `/evaluate/:docId` | Ask a question. Optional reference answer and top-K under "Advanced options". |
| `/results/:docId/:evalId` | Score cards, answer with unsupported claims highlighted, failure type, fix suggestion, retrieved chunks. |
| `/history/:docId` | All evaluations for a document, with averages, search and a failure-type filter. |

`/evaluate` and `/history` without an id show a document picker.

Score thresholds (green at or above, red below) are in `src/lib/format.js`: Context Relevance 0.5, Faithfulness 0.6, Completeness 0.5, Precision 0.4.
