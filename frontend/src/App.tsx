import { useEffect, useState } from "react";
import { useJobStream } from "./hooks/useData";
import { Overview } from "./pages/Overview";
import { Research } from "./pages/Research";
import { Concepts } from "./pages/Concepts";
import { Projects } from "./pages/Projects";
import { ProjectWorkspace } from "./pages/ProjectWorkspace";
import { Assets } from "./pages/Assets";
import { Publishing } from "./pages/Publishing";
import { Analytics } from "./pages/Analytics";
import { Costs } from "./pages/Costs";
import { Settings } from "./pages/Settings";

const NAV = [
  ["overview", "Overview"], ["research", "Keywords & Competitors"], ["concepts", "Concepts"], ["projects", "Production"],
  ["assets", "Assets"], ["publishing", "Publishing"], ["analytics", "Analytics & Growth"], ["costs", "Costs"], ["settings", "Settings"],
] as const;

const useHash = () => {
  const [h, setH] = useState(window.location.hash.slice(1) || "overview");
  useEffect(() => {
    const f = () => setH(window.location.hash.slice(1) || "overview");
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return h;
};

export default function App() {
  const route = useHash();
  const [page, arg] = route.split("/");
  const jobs = useJobStream();
  const view = (() => {
    switch (page) {
      case "research": return <Research />;
      case "concepts": return <Concepts />;
      case "projects": return arg ? <ProjectWorkspace id={arg} /> : <Projects />;
      case "assets": return <Assets />;
      case "publishing": return <Publishing />;
      case "analytics": return <Analytics />;
      case "costs": return <Costs />;
      case "settings": return <Settings />;
      default: return <Overview />;
    }
  })();
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav aria-label="Main" className="border-b border-white/10 bg-navy-900 p-3 md:w-56 md:border-b-0 md:border-r">
        <div className="mb-4 px-2">
          <div className="text-lg font-semibold text-gold">Driftbound</div>
          <div className="text-xs text-atmo">Studio · local · €0 API</div>
        </div>
        <ul className="flex flex-wrap gap-1 md:flex-col">
          {NAV.map(([k, label]) => (
            <li key={k}>
              <a href={`#${k}`} aria-current={page === k ? "page" : undefined}
                className={`block rounded-md px-2 py-1.5 text-sm ${page === k ? "bg-gold/15 text-gold" : "text-ivory/80 hover:bg-white/5"}`}>{label}</a>
            </li>
          ))}
        </ul>
        {jobs.length > 0 && (
          <div className="mt-4 rounded-md border border-white/10 p-2 text-xs" aria-live="polite">
            <div className="mb-1 text-atmo">Jobs</div>
            {jobs.map((j) => (
              <div key={j.id} className="mb-1">
                <div className="truncate">#{j.id} {j.type} <span className="text-white/40">{j.status}</span></div>
                <div className="h-1 rounded bg-white/10"><div className="h-1 rounded bg-gold" style={{ width: `${j.progress * 100}%` }} /></div>
              </div>
            ))}
          </div>
        )}
      </nav>
      <main className="min-w-0 flex-1 p-4 md:p-6">{view}</main>
    </div>
  );
}
