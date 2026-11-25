import { useState } from "react";
import { Badge, Btn, Card, Field, JsonEdit, Loading, api, inputCls } from "../components/ui";
import { useData } from "../hooks/useData";

const statusTone: Record<string, string> = { approved: "ok", draft: "info", rejected: "bad", archived: "dim", in_production: "warn" };

export function Concepts() {
  const c = useData<any[]>("/concepts");
  const kws = useData<any[]>("/keywords");
  const [open, setOpen] = useState<number | null>(null);
  const [gen, setGen] = useState({ mode: "seo", keyword_id: "", idea: "" });
  const [filter, setFilter] = useState("active");
  if (!c.data) return <Loading error={c.error} />;
  const list = c.data.filter((x) => filter === "all" || (filter === "active" ? !["archived", "rejected"].includes(x.status) : x.status === filter))
    .sort((a, b) => (b.scores?.overall ?? 0) - (a.scores?.overall ?? 0));
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Concept library</h1>
      <Card title="Generate a concept (local LLM if available, otherwise template)">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Mode"><select className={inputCls} value={gen.mode} onChange={(e) => setGen({ ...gen, mode: e.target.value })}>
            <option value="seo">SEO-driven</option><option value="competitor_gap">Competitor gap</option><option value="experimental">Experimental</option></select></Field>
          <Field label="Keyword"><select className={inputCls} value={gen.keyword_id} onChange={(e) => setGen({ ...gen, keyword_id: e.target.value })}>
            <option value="">–</option>{kws.data?.map((k) => <option key={k.id} value={k.id}>{k.keyword} ({k.opportunity_score ?? "–"})</option>)}</select></Field>
          <Field label="Idea (optional)"><input className={inputCls} value={gen.idea} onChange={(e) => setGen({ ...gen, idea: e.target.value })} /></Field>
          <Btn kind="primary" onClick={async () => { const r = await api.post("/concepts/generate", { ...gen, keyword_id: gen.keyword_id ? Number(gen.keyword_id) : null }); c.reload(); setOpen(r.id); }}>Generate</Btn>
          <Field label="Show"><select className={inputCls} value={filter} onChange={(e) => setFilter(e.target.value)}>
            {["active", "draft", "approved", "in_production", "rejected", "archived", "all"].map((s) => <option key={s}>{s}</option>)}</select></Field>
        </div>
        <p className="mt-2 text-xs text-white/50">Manual route: paste a concept JSON written in your ChatGPT/Claude subscription into "Create from JSON" below.</p>
      </Card>
      <div className="grid gap-3 lg:grid-cols-2">
        {list.map((x) => (
          <Card key={x.id} title={<span>{x.name} <Badge tone={statusTone[x.status]}>{x.status}</Badge></span>}
            actions={<>
              {x.status !== "approved" && x.status !== "in_production" && <Btn onClick={async () => { await api.post(`/concepts/${x.id}/status`, { status: "approved" }); c.reload(); }}>Approve</Btn>}
              {x.status === "approved" && <Btn kind="primary" onClick={async () => { const p = await api.post(`/concepts/${x.id}/to-project`); window.location.hash = `projects/${p.id}`; }}>Start production</Btn>}
              {x.status === "draft" && <Btn onClick={async () => { await api.post(`/concepts/${x.id}/status`, { status: "rejected" }); c.reload(); }}>Reject</Btn>}
              {x.status !== "archived" && <Btn onClick={async () => { await api.post(`/concepts/${x.id}/status`, { status: "archived" }); c.reload(); }}>Archive</Btn>}
              <Btn onClick={() => setOpen(open === x.id ? null : x.id)}>{open === x.id ? "Close" : "Brief"}</Btn>
            </>}>
            <div className="text-sm text-white/80">{x.data.environment}</div>
            <div className="mt-1 flex flex-wrap gap-1 text-xs">
              <Badge tone="info">{x.data.category}</Badge><Badge>{x.data.duration_hours} h</Badge><Badge>{x.data.primary_keyword}</Badge>
              <Badge tone={x.data.free_production_suitability === "high" ? "ok" : x.data.free_production_suitability === "low" ? "warn" : "dim"}>free production: {x.data.free_production_suitability}</Badge>
              <Badge>score {x.scores?.overall ?? "–"} ({x.scores?.kind})</Badge><Badge>{x.generated_by}</Badge>
              {x.scores?.similar_to?.length > 0 && <Badge tone="warn">similar to {x.scores.similar_to.join(", ")}</Badge>}
            </div>
            {open === x.id && <div className="mt-3 flex flex-col gap-3">
              <table><tbody>{Object.entries(x.scores ?? {}).filter(([k]) => !["kind", "missing", "similar_to"].includes(k)).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td>{v == null ? <span className="text-white/40">no data</span> : String(v)}</td></tr>))}</tbody></table>
              <JsonEdit rows={18} value={x.data} onSave={async (v) => { await api.put(`/concepts/${x.id}`, v); c.reload(); }} />
            </div>}
          </Card>
        ))}
      </div>
      <Card title="Create from JSON (manual / imported from a subscription)">
        <JsonEdit rows={8} value={{ name: "", category: "sleep", primary_keyword: "", environment: "", duration_hours: 8, scene: { audio: ["wind"], fx: ["ambient"] } }}
          onSave={async (v) => { await api.post("/concepts", v); c.reload(); }} />
      </Card>
    </div>
  );
}
