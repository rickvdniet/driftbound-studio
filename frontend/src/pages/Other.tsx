import { useState } from "react";
import { Badge, Btn, Card, Field, JsonEdit, Loading, Stat, api, eur, fmtBytes, fmtNum, inputCls, stateTone } from "../components/ui";
import { useData } from "../hooks/useData";
import { file } from "../services/api";

export function Assets() {
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const { data, error } = useData<any[]>(`/assets?${kind ? `kind=${kind}&` : ""}${q ? `q=${encodeURIComponent(q)}` : ""}`);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Asset library</h1>
      <div className="flex flex-wrap gap-2">
        <select aria-label="Kind" className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">all kinds</option>{["image", "visual_master", "audio_layer", "audio_licensed", "audio_mix", "preview", "thumbnail", "final_video"].map((k) => <option key={k}>{k}</option>)}</select>
        <input aria-label="Search" className={inputCls} placeholder="search prompt, provider, license…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!data ? <Loading error={error} /> : <Card><div className="overflow-x-auto"><table>
        <thead><tr><th>Preview</th><th>Kind</th><th>Project</th><th>Provider / model</th><th>License</th><th>Size</th><th>Hash</th><th>Cost</th></tr></thead>
        <tbody>{data.map((a) => (
          <tr key={a.id}>
            <td>{["image", "thumbnail"].includes(a.kind) ? <img alt="" src={file(a.path)} className="h-10 rounded" /> : a.kind.startsWith("audio") ? <audio controls preload="none" src={file(a.path)} className="h-8 w-40" /> : <a className="text-gold hover:underline" href={file(a.path)}>open</a>}</td>
            <td>{a.kind} <span className="text-white/40">{a.role}</span></td>
            <td><a className="hover:underline" href={`#projects/${a.project_id}`}>{a.project_id}</a></td>
            <td>{a.provider}<div className="max-w-xs truncate text-[11px] text-white/40" title={a.prompt ?? ""}>{a.model} {a.prompt}</div></td>
            <td>{a.license?.name ?? "original"} {a.commercial_ok === false && <Badge tone="bad">non-commercial</Badge>}</td>
            <td>{fmtBytes(a.size_bytes)}</td>
            <td className="font-mono text-[10px]">{a.sha256?.slice(0, 10)} {a.duplicate_count > 1 && <Badge tone="warn">×{a.duplicate_count} duplicate</Badge>}</td>
            <td>{eur(a.cost_eur)}</td></tr>))}
        </tbody></table></div></Card>}
    </div>
  );
}

export function Publishing() {
  const { data } = useData<any[]>("/projects", 10000);
  if (!data) return <Loading />;
  const groups = [["Approved / ready", ["APPROVED", "READY_FOR_UPLOAD"]], ["Private uploads", ["UPLOADING_PRIVATE", "UPLOADED_PRIVATE", "PUBLISH_APPROVED"]],
    ["Scheduled", ["SCHEDULED"]], ["Published", ["PUBLISHED"]]] as const;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Publishing calendar</h1>
      <p className="text-sm text-white/60">Every upload starts private. Publishing or scheduling needs a separate confirmation in the project. Without API credentials, use "Export YouTube upload package" and upload in YouTube Studio.</p>
      <div className="grid gap-4 lg:grid-cols-4">
        {groups.map(([title, states]) => (
          <Card key={title} title={title}>
            {data.filter((p) => (states as readonly string[]).includes(p.state)).map((p) => (
              <div key={p.id} className="mb-2 text-sm"><a className="text-gold hover:underline" href={`#projects/${p.id}`}>{p.name}</a> <Badge tone={stateTone(p.state)}>{p.state}</Badge>
                {p.youtube_video_id && <div className="text-xs text-white/50">video {p.youtube_video_id}</div>}</div>))}
          </Card>))}
      </div>
    </div>
  );
}

export function Analytics() {
  const a = useData("/analytics");
  const [f, setF] = useState<File | null>(null);
  const [period, setPeriod] = useState({ start: "", end: "" });
  const [man, setMan] = useState<any>({});
  const [fc, setFc] = useState<any>({ videos_now: 0, videos_per_month: 10, monthly_views_per_video: 300, monthly_growth_pct: 3, monetization_month: 9, monthly_operating_cost_eur: 0, production_cost_per_video_eur: 0, months: 24 });
  const [res, setRes] = useState<any>(null);
  if (!a.data) return <Loading error={a.error} />;
  const t = a.data.totals;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Analytics & growth</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Views" value={t.has_data ? fmtNum(t.views) : null} /><Stat label="Watch hours" value={t.has_data ? fmtNum(t.watch_hours) : null} />
        <Stat label="Subscribers" value={t.has_data ? fmtNum(t.subscribers) : null} /><Stat label="Revenue" value={t.has_data && t.revenue != null ? fmtNum(t.revenue, 2) : null} hint="only with authorized monetization data" />
      </div>
      <Card title="YouTube Partner Program progress">
        <div className="grid gap-3 md:grid-cols-2">{Object.entries(a.data.ypp.tiers).map(([name, tier]: any) => (
          <div key={name} className="rounded-md border border-white/10 p-3 text-sm"><div className="mb-1 font-medium">{name === "early_access" ? "Early access (expanded YPP)" : "Full ad revenue sharing"}</div>
            <div>Subscribers: {tier.subscribers.current ?? "–"} / {tier.subscribers.target} {tier.subscribers.pct != null && `(${tier.subscribers.pct}%)`}</div>
            <div>Eligible public watch hours (12 m): {tier.watch_hours.current ?? "–"} / {tier.watch_hours.target} {tier.watch_hours.pct != null && `(${tier.watch_hours.pct}%)`}</div>
            <div className="text-xs text-white/50">{tier.other}</div></div>))}</div>
        <p className="mt-2 text-xs text-white/50">{a.data.ypp.note} Requirements shown as published by YouTube; verify the current version and your region.</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Import YouTube Studio CSV (Advanced mode export)">
          <div className="flex flex-wrap items-end gap-2">
            <input aria-label="Studio CSV" type="file" accept=".csv" onChange={(e) => setF(e.target.files?.[0] ?? null)} className="text-sm" />
            <Field label="Period start"><input type="date" className={inputCls} value={period.start} onChange={(e) => setPeriod({ ...period, start: e.target.value })} /></Field>
            <Field label="Period end"><input type="date" className={inputCls} value={period.end} onChange={(e) => setPeriod({ ...period, end: e.target.value })} /></Field>
            <Btn disabled={!f || !period.start || !period.end} onClick={async () => { const fd = new FormData(); fd.append("file", f!); fd.append("period_start", period.start); fd.append("period_end", period.end); await api.post("/analytics/import", fd); a.reload(); }}>Import</Btn>
          </div>
        </Card>
        <Card title="Manual channel snapshot (from Studio → Earn / Overview)">
          <div className="grid grid-cols-2 gap-2">{["subscribers", "views", "watch_hours", "eligible_public_watch_hours_12m", "revenue"].map((k) => (
            <Field key={k} label={k}><input type="number" className={inputCls} value={man[k] ?? ""} onChange={(e) => setMan({ ...man, [k]: e.target.value })} /></Field>))}</div>
          <div className="mt-2"><Btn onClick={async () => { await api.post("/analytics/manual", { metrics: man }); a.reload(); }}>Save snapshot</Btn></div>
        </Card>
      </div>
      {t.has_data && t.videos?.length > 0 && <Card title="Video performance (imported data)"><table><thead><tr><th>Video</th><th>Project</th><th>Views</th><th>Watch h</th><th>Subs gained</th></tr></thead><tbody>
        {t.videos.map((v: any) => <tr key={v.video_id}><td>{v.title ?? v.video_id}</td><td>{v.project_id ?? "–"}</td><td>{fmtNum(v.views)}</td><td>{fmtNum(v.watch_hours, 1)}</td><td>{fmtNum(v.subscribers_gained)}</td></tr>)}
      </tbody></table></Card>}
      <Card title="Business case calculator (illustrative)">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">{Object.keys(fc).map((k) => (
          <Field key={k} label={k.replace(/_/g, " ")}><input type="number" className={inputCls} value={fc[k]} onChange={(e) => setFc({ ...fc, [k]: +e.target.value })} /></Field>))}</div>
        <div className="mt-2"><Btn onClick={async () => setRes(await api.post("/analytics/forecast", fc))}>Calculate</Btn></div>
        {res && <div className="mt-3"><p className="text-xs text-amber-200">{res._label} RPM scenarios (€0.50 / €2 / €5) are modeling assumptions, not benchmarks.</p>
          <table><thead><tr><th>Scenario</th><th>RPM</th><th>Revenue last 12 months</th><th>Cumulative surplus</th><th>Break-even views / month</th><th>Payback</th></tr></thead><tbody>
            {["conservative", "base", "optimistic"].map((s) => <tr key={s}><td>{s}</td><td>{eur(res[s].rpm_eur)}</td><td>{eur(res[s].annual_revenue_last12_eur)}</td><td>{eur(res[s].cumulative_surplus_eur)}</td><td>{fmtNum(res[s].break_even_monthly_views)}</td><td>{String(res[s].payback_month ?? "not within horizon")}</td></tr>)}
          </tbody></table></div>}
      </Card>
    </div>
  );
}

export function Costs() {
  const { data, error } = useData("/costs", 10000);
  if (!data) return <Loading error={error} />;
  const b = data.budget;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Costs & resources</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="API spend this month" value={eur(data.month_api_spend_eur)} hint={`budget ${eur(b.monthly_api_budget_eur)}`} />
        <Stat label="Paid APIs" value={b.paid_api_enabled ? "ENABLED" : "disabled"} hint={`auto paid fallback: ${b.paid_fallback_enabled ? "on" : "off"}`} />
        <Stat label="Local render time" value={`${data.local_render_hours} h`} />
        <Stat label="Electricity (estimate)" value={eur(data.by_category.electricity ?? 0)} hint={b.electricity_eur_per_kwh ? `${b.render_power_watts} W × €${b.electricity_eur_per_kwh}/kWh` : "set assumptions in Settings → Budget"} />
      </div>
      <Card title="By category (API spend is separate from estimated local costs)">
        <table><tbody>{Object.entries(data.by_category).map(([k, v]: any) => <tr key={k}><td>{k}</td><td>{eur(v)}</td><td>{k === "api" ? "actual/committed" : "estimate"}</td></tr>)}
          {!Object.keys(data.by_category).length && <tr><td className="text-white/50">No costs recorded yet.</td></tr>}</tbody></table>
      </Card>
      <Card title="By project"><table><tbody>{Object.entries(data.by_project).map(([k, v]: any) => <tr key={k}><td>{k}</td><td>{eur(v)}</td></tr>)}</tbody></table></Card>
      <Card title="Existing subscriptions (allocated, not marginal API spend)">
        <JsonEdit rows={5} value={b.existing_subscriptions} onSave={(v) => api.put("/settings/budget", { existing_subscriptions: v })} />
      </Card>
    </div>
  );
}

export function Settings() {
  const s = useData("/settings");
  const hw = useData("/hardware");
  const providers = useData<any[]>("/providers");
  if (!s.data) return <Loading error={s.error} />;
  const save = (k: string) => async (v: any) => { await api.put(`/settings/${k}`, v); s.reload(); };
  const h = hw.data;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <Card title="Hardware & local AI" actions={<Btn kind="primary" onClick={async () => { hw.setData(await api.post("/hardware/scan")); }}>Scan this computer</Btn>}>
        {h?.cpu_model ? <div className="grid gap-3 lg:grid-cols-2 text-sm">
          <div>
            <div>{h.os} {h.os_release} {h.wsl && <Badge tone="info">WSL2</Badge>} · {h.cpu_model}</div>
            <div>{h.cpu_cores_physical} cores / {h.cpu_threads} threads · RAM {h.ram_total_gb} GB ({h.ram_available_gb} free) · disk {h.disk_free_gb} GB free</div>
            <div>GPU: {h.gpus.length ? h.gpus.map((g: any) => `${g.vendor} ${g.name} ${g.vram_gb ?? "?"} GB`).join(", ") : "none detected"}</div>
            <div>Python {h.python} · Node {h.node ?? "–"} · FFmpeg {h.ffmpeg ? "yes" : "NO"}</div>
            <div>Encoders that actually work: {Object.entries(h.encoders).filter(([, v]: any) => v.works).map(([k]) => k).join(", ") || "–"}</div>
            <div>Ollama: {h.ollama.reachable ? `running (${h.ollama.models.join(", ") || "no models"})` : h.ollama.binary ? "installed, not running" : "not found"} · ComfyUI: {h.comfyui.reachable ? "running" : "not reachable"}</div>
            {h.container_hint && <div className="mt-1 text-xs text-amber-200">Looks like a container/VM: results describe this environment, not necessarily your desktop.</div>}
          </div>
          <table><tbody>{Object.entries(h.assessment).map(([k, v]: any) => (
            <tr key={k}><td>{k.replace(/_/g, " ")}</td><td><Badge tone={v.level === "good" ? "ok" : v.level === "limited" ? "warn" : "bad"}>{v.level}</Badge></td><td className="text-xs">{v.why}<div className="text-white/50">{v.recommendation}</div></td></tr>))}</tbody></table>
        </div> : <p className="text-sm text-white/50">Not scanned yet. Model downloads are never started automatically.</p>}
      </Card>
      <Card title="Providers"><table><thead><tr><th>Kind</th><th>Provider</th><th>Where</th><th>Cost</th><th>Status</th><th>Notes</th></tr></thead><tbody>
        {providers.data?.map((p) => <tr key={p.kind + p.name}><td>{p.kind}</td><td>{p.name}</td><td>{p.local ? "local" : "external"}</td><td>{p.paid ? <Badge tone="warn">paid · disabled</Badge> : <Badge tone="ok">€0</Badge>}</td><td>{p.status}</td><td className="text-xs text-white/60">{p.notes}</td></tr>)}
      </tbody></table></Card>
      <div className="grid gap-4 xl:grid-cols-2">
        {[["brand", "Brand (used everywhere; nothing is hardcoded)"], ["providers", "Provider selection & local models"], ["render", "Rendering & encoding"],
          ["audio_profiles", "Audio profiles (product defaults, not YouTube requirements)"], ["publishing", "Publishing (set made_for_kids_confirmed to true/false)"],
          ["research", "Research limits & retention"], ["scoring_weights", "Opportunity scoring weights"], ["automation", "Automation mode"]].map(([k, title]) => (
          <Card key={k} title={title}><JsonEdit rows={k === "brand" ? 18 : 8} value={s.data[k]} onSave={save(k)} /></Card>))}
        <Card title="Budget (paid APIs stay off unless you opt in)">
          <BudgetEditor value={s.data.budget} onSaved={s.reload} />
        </Card>
      </div>
      <Card title="Backup"><Btn onClick={async () => { const r = await api.post("/backup"); alert(`Database backup: workspace/${r.backup} (${fmtBytes(r.bytes)})`); }}>Back up database now</Btn></Card>
    </div>
  );
}

function BudgetEditor({ value, onSaved }: { value: any; onSaved: () => void }) {
  const [v, setV] = useState(value);
  return (
    <div className="flex flex-col gap-2 text-sm">
      <label><input type="checkbox" checked={v.paid_api_enabled} onChange={(e) => setV({ ...v, paid_api_enabled: e.target.checked })} /> Allow paid API usage (explicit opt-in)</label>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Monthly API budget €"><input type="number" className={inputCls} value={v.monthly_api_budget_eur} onChange={(e) => setV({ ...v, monthly_api_budget_eur: +e.target.value })} /></Field>
        <Field label="Per-project API budget €"><input type="number" className={inputCls} value={v.per_project_api_budget_eur} onChange={(e) => setV({ ...v, per_project_api_budget_eur: +e.target.value })} /></Field>
        <Field label="Electricity €/kWh"><input type="number" step="0.01" className={inputCls} value={v.electricity_eur_per_kwh ?? ""} onChange={(e) => setV({ ...v, electricity_eur_per_kwh: e.target.value ? +e.target.value : null })} /></Field>
        <Field label="Render power draw (W, your estimate)"><input type="number" className={inputCls} value={v.render_power_watts ?? ""} onChange={(e) => setV({ ...v, render_power_watts: e.target.value ? +e.target.value : null })} /></Field>
      </div>
      <div><Btn kind={v.paid_api_enabled ? "danger" : "default"} onClick={async () => {
        if (v.paid_api_enabled && !window.confirm("Enable paid APIs? Each paid job still needs its own approval and must fit the budget.")) return;
        await api.put("/settings/budget", { ...v, confirm_paid: v.paid_api_enabled }); onSaved();
      }}>Save budget</Btn></div>
    </div>
  );
}
