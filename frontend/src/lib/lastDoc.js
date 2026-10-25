// Remembers the most recently used document so the nav links have somewhere to go.
const KEY = "ragdiag:lastDoc";

export function getLastDoc() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setLastDoc(docId) {
  try {
    if (docId) localStorage.setItem(KEY, docId);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable — nav falls back to the document picker */
  }
}
