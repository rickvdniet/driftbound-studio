import { useState } from "react";
import { Badge, Btn, Card, Field, Loading, api, fmtNum, inputCls } from "../components/ui";
import { useData } from "../hooks/useData";

const kindTone: Record<string, string> = { verified: "ok", third_party_estimate: "info", relative_interest: "warn", proxy: "warn", heuristic: "dim", manual: "dim" };

export function Research() {
  const kws = useData<any[]>("/keywords");
  const vids = useData<any[]>("/competitors/videos");
  const quota = useData("/research/quota");
  const [sel, setSel] = useState<any | null>(null);
  const [nk, setNk] = useState({ keyword: "", cluster: "manual", est_monthly_volume: "", volume_source: "" });
  const [file, setFile] = useState<File | null>(null);
  const [imp, setImp] = useState({ source: "vidiq", kind: "third_party_estimate" });
  if (!kws.data) return <Loading error={kws.error} />;
  const clusters = [...new Set(kws.data.map((k) => k.cluster))];
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Keyword research & competitors</h1>
      <p className="text-sm text-white/60">Demand figures are shown only with their source. YouTube does not publish exact search volumes; Google Trends gives relative interest only; competitor views are a proxy (traffic may come from recommendations).</p>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Add keyword">
          <div className="flex flex-col gap-2">
            <Field label="Keyword"><input className={inputCls} value={nk.keyword} onChange={(e) => setNk({ ...nk, keyword: e.target.value })} /></Field>
            <Field label="Cluster"><input className={inputCls} value={nk.cluster} onChange={(e) => setNk({ ...nk, cluster: e.target.value })} /></Field>
            <Field label="Monthly volume (only if you have a source)"><input className={inputCls} value={nk.est_monthly_volume} onChange={(e) => setNk({ ...nk, est_monthly_volume: e.target.value })} /></Field>
            <Field label="Volume source"><input className={inputCls} value={nk.volume_source} onChange={(e) => setNk({ ...nk, volume_source: e.target.value })} /></Field>
            <div><Btn kind="primary" disabled={!nk.keyword} onClick={async () => {
              await api.post("/keywords", { ...nk, est_monthly_volume: nk.est_monthly_volume ? Number(nk.est_monthly_volume) : null, volume_source: nk.volume_source || null });
              setNk({ ...nk, keyword: "", est_monthly_volume: "" }); kws.reload();
            }}>Add</Btn></div>
          </div>
        </Card>
        <Card title="Import CSV (vidIQ, TubeBuddy, Google Trends, Studio search terms)">
          <div className="flex flex-col gap-2">
            <input aria-label="CSV file" type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            <Field label="Source name"><input className={inputCls} value={imp.source} onChange={(e) => setImp({ ...imp, source: e.target.value })} /></Field>
            <Field label="What the numbers are">
              <select className={inputCls} value={imp.kind} onChange={(e) => setImp({ ...imp, kind: e.target.value })}>
                <option value="third_party_estimate">Third-party volume estimate</option>
                <option value="relative_interest">Relative interest (Google Trends 0–100)</option>
                <option value="verified">Verified (authorized YouTube Analytics search terms)</option>
              </select>
            </Field>
            <div><Btn disabled={!file} onClick={async () => {
              const fd = new FormData(); fd.append("file", file!); fd.append("source", imp.source); fd.append("kind", imp.kind);
              const r = await api.post("/keywords/import", fd); alert(`Imported: ${r.created} new, ${r.updated} updated`); kws.reload();
            }}>Import</Btn></div>
          </div>
        </Card>
        <Card title="YouTube Data API (free quota)">
          {quota.data && <div className="text-sm">
            <div>API key: {quota.data.api_key_configured ? <Badge tone="ok">configured</Badge> : <Badge tone="warn">not set (DRIFTBOUND_YOUTUBE_API_KEY)</Badge>}</div>
            <div className="mt-1">Units used today: {quota.data.units_today} / {quota.data.limit}</div>
            <p className="mt-2 text-xs text-white/50">"Collect competitors" on a keyword runs 1 search (100 units) + video and channel lookups (~2 units). Results are cached; data older than the retention window is purged.</p>
            <div className="mt-2"><Btn onClick={async () => { const r = await api.post("/research/purge"); alert(`Purged ${r.purged_videos} stale videos`); }}>Purge expired API data</Btn></div>
          </div>}
        </Card>
      </div>
      {clusters.map((c) => (
        <Card key={c} title={`Cluster: ${c}`}>
          <div className="overflow-x-auto"><table>
            <thead><tr><th>Keyword</th><th>Score</th><th>Confidence</th><th>Demand</th><th>Sampled</th><th>Median views/day</th><th>Median subs</th><th>Small-ch. success</th><th /></tr></thead>
            <tbody>{kws.data!.filter((k) => k.cluster === c).sort((a, b) => (b.opportunity_score ?? -1) - (a.opportunity_score ?? -1)).map((k) => (
              <tr key={k.id} className="hover:bg-white/5">
                <td><button className="text-left text-gold hover:underline" onClick={() => setSel(k)}>{k.keyword}</button></td>
                <td>{k.opportunity_score ?? "–"}</td>
                <td><Badge tone={(k.confidence ?? 0) > 0.5 ? "ok" : "warn"}>{k.confidence ?? 0}</Badge></td>
                <td>{k.est_monthly_volume ? <>{fmtNum(k.est_monthly_volume)} <Badge tone={kindTone[k.volume_kind]}>{k.volume_source}</Badge></> : k.trend_interest != null ? <Badge tone="warn">trend {k.trend_interest}</Badge> : <span className="text-white/30">missing</span>}</td>
                <td>{k.sampled_videos ?? "–"}</td><td>{fmtNum(k.median_views_per_day)}</td><td>{fmtNum(k.median_channel_subs)}</td>
                <td>{k.small_channel_success != null ? `${Math.round(k.small_channel_success * 100)}%` : "–"}</td>
                <td><Btn disabled={!quota.data?.api_key_configured} title="Uses ~102 free quota units" onClick={async () => { await api.post("/research/collect", { keyword_id: k.id }); kws.reload(); vids.reload(); quota.reload(); }}>Collect competitors</Btn></td>
              </tr>))}
            </tbody></table></div>
        </Card>
      ))}
      {sel && (
        <Card title={`Evidence: ${sel.keyword}`} actions={<Btn onClick={() => setSel(null)}>Close</Btn>}>
          <table><thead><tr><th>Component</th><th>Value</th><th>Weight used</th><th>Kind</th><th>Evidence</th></tr></thead><tbody>
            {Object.entries(sel.score_breakdown?.breakdown ?? {}).map(([n, b]: any) => (
              <tr key={n}><td>{n}</td><td>{b.value}</td><td>{b.weight_used}</td><td><Badge tone={kindTone[b.kind]}>{b.kind}</Badge></td><td>{b.evidence}</td></tr>))}
          </tbody></table>
          <p className="mt-2 text-xs text-white/50">Missing: {(sel.score_breakdown?.missing ?? []).join(", ") || "none"}. {sel.score_breakdown?.note}</p>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            {(["evergreen", "differentiation", "feasibility"] as const).map((f) => (
              <Field key={f} label={`${f} (manual 0–1)`}>
                <input className={inputCls} type="number" step="0.05" min="0" max="1" defaultValue={sel[f] ?? ""}
                  onBlur={async (e) => { const v = e.target.value === "" ? null : Number(e.target.value); const r = await api.patch(`/keywords/${sel.id}`, { [f]: v }); setSel(r); kws.reload(); }} />
              </Field>))}
          </div>
        </Card>
      )}
      <Card title="Competitor videos">
        {!vids.data?.length ? <p className="text-sm text-white/50">No competitor data yet. Collect for a keyword above (needs a free API key).</p> : (
          <div className="overflow-x-auto"><table>
            <thead><tr><th>Video</th><th>Channel</th><th>Subs</th><th>Views</th><th>Age (d)</th><th>Lifetime views/day</th><th>Measured recent/day</th><th>Views/sub</th><th>Flags</th></tr></thead>
            <tbody>{vids.data.sort((a, b) => (b.lifetime_views_per_day ?? 0) - (a.lifetime_views_per_day ?? 0)).map((v) => (
              <tr key={v.video_id}><td className="max-w-xs truncate"><a className="hover:underline" href={`https://www.youtube.com/watch?v=${v.video_id}`} target="_blank" rel="noreferrer">{v.title}</a></td>
                <td>{v.channel}</td><td>{v.subscribers == null ? <Badge>hidden</Badge> : fmtNum(v.subscribers)}</td><td>{fmtNum(v.views)}</td>
                <td>{fmtNum(v.age_days)}</td><td>{fmtNum(v.lifetime_views_per_day)}</td>
                <td>{v.measured_recent_views_per_day == null ? <span className="text-white/30">needs 2 snapshots</span> : fmtNum(v.measured_recent_views_per_day)}</td>
                <td>{v.views_per_subscriber ?? "–"}</td>
                <td>{v.outperformer && <Badge tone="ok">outperformer</Badge>} {v.small_channel && <Badge tone="info">small channel</Badge>}</td></tr>))}
            </tbody></table></div>)}
        <p className="mt-2 text-xs text-white/40">Use competitors to understand demand, never to copy titles, thumbnails, audio or compositions.</p>
      </Card>
    </div>
  );
}
