import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { getHealth } from "../api/client";
import { getLastDoc } from "../lib/lastDoc";

function HealthDot() {
  const [state, setState] = useState("checking");

  useEffect(() => {
    let alive = true;
    const check = () =>
      getHealth()
        .then((h) => alive && setState(h?.status === "ok" ? "ok" : "degraded"))
        .catch(() => alive && setState("down"));
    check();
    const id = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const styles = {
    checking: ["bg-slate-400", "Checking API"],
    ok: ["bg-emerald-400", "API online"],
    degraded: ["bg-amber-400", "API degraded"],
    down: ["bg-red-500", "API offline"],
  }[state];

  return (
    <span className="hidden items-center gap-2 text-xs text-navy-200 sm:inline-flex" title={styles[1]}>
      <span className={`h-2 w-2 rounded-full ${styles[0]}`} />
      {styles[1]}
    </span>
  );
}

export default function Layout() {
  const { pathname } = useLocation(); // re-renders on navigation, so lastDoc stays current
  const lastDoc = getLastDoc();

  const links = [
    { to: "/", label: "Upload", active: pathname === "/" },
    {
      to: lastDoc ? `/evaluate/${lastDoc}` : "/evaluate",
      label: "Evaluate",
      active: pathname.startsWith("/evaluate"),
    },
    {
      to: lastDoc ? `/history/${lastDoc}` : "/history",
      label: "History",
      active: pathname.startsWith("/history") || pathname.includes("/results/"),
    },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 bg-navy-950 shadow-sm">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/favicon.svg" alt="" className="h-8 w-8 rounded-md ring-1 ring-white/20" />
            <span className="text-lg font-bold tracking-tight text-white">RAGDiag</span>
          </Link>
          <nav className="flex items-center gap-1">
            {links.map((l) => (
              <Link
                key={l.label}
                to={l.to}
                aria-current={l.active ? "page" : undefined}
                className={`rounded-md px-3 py-2 text-sm font-medium transition ${
                  l.active ? "bg-white/10 text-white" : "text-navy-200 hover:bg-white/5 hover:text-white"
                }`}
              >
                {l.label}
              </Link>
            ))}
          </nav>
          <HealthDot />
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-5 text-xs text-slate-500 sm:px-6">
          RAGDiag · RAG pipeline evaluation
        </div>
      </footer>
    </div>
  );
}
