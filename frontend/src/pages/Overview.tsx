import { Badge, Card, Loading, Stat, eur, fmtBytes, fmtNum } from "../components/ui";
import { useData } from "../hooks/useData";

export function Overview() {
  const { data: o, error } = useData("/overview", 5000);
  if (!o) return <Loading error={error} />;
  const a = o.analytics;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Overview</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Projects" value={o.projects} />
        <Stat label="In production" value={o.in_production} />
        <Stat label="Awaiting approval" value={o.awaiting_approval} />
        <Stat label="Published" value={o.published} hint={`${o.scheduled} scheduled`} />
        <Stat label="Failed jobs" value={o.failed_jobs} />
        <Stat label="API spend this month" value={eur(o.api_spend_month_eur)} hint={`budget ${eur(o.budget.monthly_api_budget_eur)} · paid ${o.budget.paid_api_enabled ? "ENABLED" : "disabled"}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Channel performance">
          {a.has_data ? (
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Views" value={fmtNum(a.views)} hint={`as of ${a.as_of ?? "–"} · ${a.sources.join(", ")}`} />
              <Stat label="Watch hours" value={fmtNum(a.watch_hours)} />
              <Stat label="Subscribers" value={fmtNum(a.subscribers)} />
              <Stat label="Eligible public watch hours (12 m)" value={fmtNum(a.eligible_public_watch_hours_12m)} />
            </div>
          ) : <p className="text-sm text-white/50">No analytics imported yet. Real data only: connect YouTube Analytics or import a Studio CSV (Analytics page).</p>}
        </Card>
        <Card title="Next content opportunities">
          <table><tbody>
            {o.opportunities.map((k: any) => (
              <tr key={k.keyword}><td>{k.keyword}</td><td className="text-right">{k.score}</td><td><Badge tone={k.confidence > 0.5 ? "ok" : "warn"}>conf {k.confidence}</Badge></td></tr>
            ))}
          </tbody></table>
          <p className="mt-2 text-[11px] text-white/40">Scores use only available data. Low confidence means mostly heuristics; import research to improve.</p>
        </Card>
        <Card title="Local resources">
          <div className="text-sm">
            {o.hardware ? <>
              <div>{o.hardware.cpu_model} · {o.hardware.cpu_threads} threads · {o.hardware.ram_total_gb} GB RAM</div>
              <div className="text-white/60">GPU: {o.hardware.gpus?.length ? o.hardware.gpus.map((g: any) => `${g.name} (${g.vram_gb ?? "?"} GB)`).join(", ") : "none detected"}</div>
            </> : <div className="text-white/50">Run a hardware scan in Settings.</div>}
            <div className="mt-2">Workspace: {fmtBytes(o.storage.total_used)} used · {fmtBytes(o.storage.disk_free)} free</div>
          </div>
        </Card>
      </div>
      <Card title="Recent production activity">
        <table><thead><tr><th>When</th><th>Project</th><th>Change</th><th>By</th></tr></thead><tbody>
          {o.recent.map((t: any) => (
            <tr key={t.id}><td className="whitespace-nowrap text-white/50">{new Date(t.at).toLocaleString()}</td>
              <td><a className="text-gold hover:underline" href={`#projects/${t.project_id}`}>{t.project_id}</a></td>
              <td>{t.from_state} → <b>{t.to_state}</b> <span className="text-white/40">{t.note}</span></td><td>{t.actor}</td></tr>
          ))}
        </tbody></table>
      </Card>
    </div>
  );
}
