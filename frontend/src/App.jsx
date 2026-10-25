import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { EmptyState } from "./components/ui";
import Evaluate from "./pages/Evaluate";
import History from "./pages/History";
import Home from "./pages/Home";
import Results from "./pages/Results";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="evaluate" element={<Evaluate />} />
        <Route path="evaluate/:docId" element={<Evaluate />} />
        <Route path="results/:docId/:evalId" element={<Results />} />
        <Route path="history" element={<History />} />
        <Route path="history/:docId" element={<History />} />
        <Route
          path="*"
          element={
            <EmptyState title="Page not found" action={<Link to="/" className="btn-primary">Go home</Link>}>
              That page doesn't exist.
            </EmptyState>
          }
        />
      </Route>
    </Routes>
  );
}
