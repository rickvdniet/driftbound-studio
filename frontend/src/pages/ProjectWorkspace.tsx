import { useEffect, useRef, useState } from "react";
import { Badge, Btn, Card, Field, JsonEdit, Loading, Progress, api, confirmThen, eur, fmtBytes, inputCls, stateTone } from "../components/ui";
import { useData } from "../hooks/useData";
import { file } from "../services/api";

const DURATIONS: [string, number][] = [["30 s (test)", 30], ["1 min", 60], ["10 min", 600], ["1 h", 3600], ["2 h", 7200], ["3 h", 10800], ["4 h", 14400], ["8 h", 28800]];
const EFFECT_TYPES = ["particles", "stars", "fog", "glow", "caustics", "shimmer", "window_droplets"];
const LAYER_TYPES = ["noise", "hum", "ventilation", "wind", "ocean", "drone", "rain", "fire", "rhythm", "thunder", "underwater"];

export function ProjectWorkspace({ id }: { id: string }) {
  const { data: p, error, reload } = useData<any>(`/projects/${id}`, 3000);
  if (!p) return <Loading error={error} />;
  const assets = (k: string) => p.assets.filter((a: any) => a.kind === k);
  const running = p.jobs.find((j: any) => ["queued", "running"].includes(j.status));
  const d = p.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <a href="#projects" className="text-sm text-atmo hover:underline">← Production</a>
        <h1 className="text-2xl font-semibold">{p.name}</h1>
        <Badge tone={stateTone(p.state)}>{p.state}</Badge>
        <Badge>API cost {eur(p.api_cost_eur)}</Badge>
        <Badge>{d.render.duration_hours} h · {d.render.width}×{d.render.height} @ {d.render.fps} fps</Badge>
        <div className="ml-auto flex gap-2">
          {!["PAUSED", "ARCHIVED"].includes(p.state)
            ? <Btn onClick={() => api.post(`/projects/${id}/state`, { state: "PAUSED" }).then(reload)}>Pause</Btn>
            : <Btn onClick={() => api.post(`/projects/${id}/state`, { state: "IMAGE_APPROVED" }).then(reload)}>Resume</Btn>}
          <Btn onClick={() => confirmThen("Archive this project? Files are kept.", () => api.post(`/projects/${id}/state`, { state: "ARCHIVED" }).then(reload))}>Archive</Btn>
        </div>
      </div>
      {running && <Card title={`Job #${running.id}: ${running.type}`} actions={<Btn kind="danger" onClick={() => api.post(`/jobs/${running.id}/cancel`).then(reload)}>Cancel</Btn>}>
        <Progress value={running.progress} label={running.message ?? running.status} /></Card>}
      {d.last_error && !running && <Card title="Last error"><div className="text-sm text-rose-300">{d.last_error.type}: {d.last_error.error}</div>
        <div className="mt-2"><Btn onClick={() => api.post(`/jobs/${d.last_error.job}/retry`).then(reload)}>Retry that stage</Btn></div></Card>}

      <Brief brief={d.brief} />
      <Images p={p} images={assets("image")} reload={reload} />
      {d.approved_image_asset_id && <>
        <Masks p={p} reload={reload} />
        <Animation p={p} reload={reload} />
        <Audio p={p} stems={assets("audio_layer")} reload={reload} />
        <PreviewStage p={p} reload={reload} />
      </>}
      {p.preview_approved && <RenderStage p={p} reload={reload} />}
      {d.qa_technical && <Review p={p} thumbs={assets("thumbnail").filter((t: any) => t.role !== "history")} reload={reload} />}
      <Provenance p={p} />
    </div>
  );
}

function Brief({ brief }: { brief: any }) {
  const [open, setOpen] = useState(false);
  return (
    <Card title="Creative brief" actions={<Btn onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</Btn>}>
      <div className="text-sm">{brief.environment}</div>
      <div className="mt-1 flex flex-wrap gap-1"><Badge tone="info">{brief.primary_keyword}</Badge>{brief.secondary_keywords.map((k: string) => <Badge key={k}>{k}</Badge>)}</div>
      {open && <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
        {["creative_direction", "unique_selling_point", "image_prompt", "negative_prompt", "thumbnail_direction", "originality_notes"].map((k) => (
          <div key={k}><div className="text-xs text-atmo">{k.replace(/_/g, " ")}</div><div className="whitespace-pre-wrap">{brief[k]}</div></div>))}
        <div><div className="text-xs text-atmo">audio layers</div>{brief.audio_layers.join(", ")}</div>
        <div><div className="text-xs text-atmo">animated elements</div>{brief.animated_elements.join(", ")}</div>
      </div>}
    </Card>
  );
}

function Images({ p, images, reload }: { p: any; images: any[]; reload: () => void }) {
  const [f, setF] = useState<File | null>(null);
  const [lic, setLic] = useState({ name: "user-owned", creator: "", source_url: "", ai_generated: false, realistic: false, commercial_use: true });
  const [prov, setProv] = useState("procedural");
  return (
    <Card title="1 · Visual direction" actions={<>
      <select aria-label="Image provider" className={inputCls} value={prov} onChange={(e) => setProv(e.target.value)}>
        <option value="procedural">Procedural painter (space scenes)</option><option value="comfyui">ComfyUI (local)</option></select>
      <Btn onClick={() => api.post(`/projects/${p.id}/images/generate`, { provider: prov, count: 3 }).then(reload)}>Generate 3 candidates</Btn></>}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {images.map((a) => (
          <figure key={a.id} className={`overflow-hidden rounded-lg border ${a.role === "approved" ? "border-gold" : "border-white/10"}`}>
            <img src={file(a.path)} alt={`Candidate ${a.id}`} className="aspect-video w-full object-cover" />
            <figcaption className="flex flex-wrap items-center gap-2 p-2 text-xs">
              <Badge tone={a.role === "approved" ? "ok" : "dim"}>{a.role}</Badge><span>{a.provider}{a.seed != null ? ` · seed ${a.seed}` : ""}</span>
              <span>{a.width}×{a.height}</span>
              {a.width && a.width / a.height < 1.7 && <Badge tone="warn">not 16:9: will be cropped, never stretched</Badge>}
              {a.role !== "approved" && <Btn kind="primary" onClick={() => api.post(`/projects/${p.id}/images/${a.id}/approve`).then(reload)}>Approve</Btn>}
            </figcaption>
            {a.meta?.quality_note && <div className="px-2 pb-2 text-[11px] text-amber-200/80">{a.meta.quality_note}</div>}
          </figure>))}
      </div>
      <div className="mt-4 grid gap-2 border-t border-white/10 pt-3 md:grid-cols-4">
        <Field label="Import image (own art or from a subscription)"><input type="file" accept="image/*" onChange={(e) => setF(e.target.files?.[0] ?? null)} className="text-sm" /></Field>
        <Field label="License"><select className={inputCls} value={lic.name} onChange={(e) => setLic({ ...lic, name: e.target.value })}>
          {["user-owned", "CC0-1.0", "CC-BY-4.0", "pixabay-content-license", "custom"].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Creator / source URL"><input className={inputCls} value={lic.creator} onChange={(e) => setLic({ ...lic, creator: e.target.value })} placeholder="creator" />
          <input className={inputCls} value={lic.source_url} onChange={(e) => setLic({ ...lic, source_url: e.target.value })} placeholder="https://…" /></Field>
        <div className="flex flex-col gap-1 text-xs">
          <label><input type="checkbox" checked={lic.ai_generated} onChange={(e) => setLic({ ...lic, ai_generated: e.target.checked })} /> AI-generated</label>
          <label><input type="checkbox" checked={lic.realistic} onChange={(e) => setLic({ ...lic, realistic: e.target.checked })} /> Looks realistic</label>
          <Btn disabled={!f} onClick={async () => { const fd = new FormData(); fd.append("file", f!); fd.append("license", JSON.stringify(lic)); await api.post(`/projects/${p.id}/images/import`, fd); reload(); }}>Import</Btn>
        </div>
      </div>
    </Card>
  );
}

function Masks({ p, reload }: { p: any; reload: () => void }) {
  const anim = p.data.animation;
  const masks = anim.masks ?? {};
  const used = [...new Set(anim.effects.map((e: any) => e.mask).filter((m: any) => typeof m === "string"))] as string[];
  const [name, setName] = useState(used.find((u) => !masks[u]) ?? "sky");
  const [pts, setPts] = useState<number[][]>([]);
  const [polys, setPolys] = useState<number[][][]>([]);
  const [bust, setBust] = useState(0);
  const img = p.assets.find((a: any) => a.id === p.data.approved_image_asset_id);
  const ref = useRef<HTMLImageElement>(null);
  const save = async (spec: any) => { await api.put(`/projects/${p.id}/config`, { animation: { ...anim, masks: { ...masks, [name]: spec } } }); setBust(Date.now()); reload(); };
  return (
    <Card title="2 · Region masks">
      <div className="mb-2 flex flex-wrap gap-1 text-xs">
        {used.map((u) => <button key={u} onClick={() => setName(u)}><Badge tone={masks[u] ? "ok" : "warn"}>{u}{masks[u] ? "" : " (undefined → full frame)"}</Badge></button>)}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="relative">
            <img ref={ref} src={file(img?.path)} alt="Click to add polygon points" className="w-full cursor-crosshair rounded"
              onClick={(e) => { const r = (e.target as HTMLImageElement).getBoundingClientRect(); setPts([...pts, [+((e.clientX - r.left) / r.width).toFixed(4), +((e.clientY - r.top) / r.height).toFixed(4)]]); }} />
            <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1 1" preserveAspectRatio="none">
              {[...polys, pts].map((pl, i) => <polygon key={i} points={pl.map((q) => q.join(",")).join(" ")} fill="rgba(217,201,160,0.25)" stroke="#D9C9A0" strokeWidth={0.003} />)}
            </svg>
          </div>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <Field label="Mask name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Btn disabled={pts.length < 3} onClick={() => { setPolys([...polys, pts]); setPts([]); }}>Close polygon</Btn>
            <Btn onClick={() => { setPts([]); setPolys([]); }}>Clear</Btn>
            <Btn kind="primary" disabled={!polys.length} onClick={() => save({ polygons: polys, feather: 0.006 })}>Save mask "{name}"</Btn>
          </div>
          <p className="mt-1 text-xs text-white/50">Click points on the image, then "Close polygon". Several polygons can form one mask. PNG masks: set {"{"}"png": "projects/{p.id}/masks/x.png"{"}"} in the JSON.</p>
        </div>
        <div>
          {masks[name] && <img alt={`Mask preview ${name}`} className="w-full rounded" src={`/api/projects/${p.id}/mask-preview?name=${encodeURIComponent(name)}&v=${bust}`} />}
          <div className="mt-2"><JsonEdit key={name + bust} rows={6} value={masks[name] ?? { polygons: [], feather: 0.006, invert: false }} onSave={save} /></div>
        </div>
      </div>
    </Card>
  );
}

function Animation({ p, reload }: { p: any; reload: () => void }) {
  const anim = p.data.animation;
  const [t, setT] = useState(0);
  const [bust, setBust] = useState(0);
  const put = async (effects: any[]) => { await api.put(`/projects/${p.id}/config`, { animation: { ...anim, effects } }); reload(); };
  const setFx = (i: number, patch: any) => put(anim.effects.map((e: any, j: number) => (j === i ? { ...e, ...patch } : e)));
  return (
    <Card title="3 · Procedural animation (fixed camera, seamless loop)" actions={<>
      <select aria-label="Add effect" className={inputCls} onChange={(e) => { if (e.target.value) put([...anim.effects, { type: e.target.value, id: `${e.target.value}_${anim.effects.length}`, mask: null, params: {}, seed: anim.effects.length + 1 }]); e.target.value = ""; }}>
        <option value="">+ add effect</option>{EFFECT_TYPES.map((x) => <option key={x}>{x}</option>)}</select></>}>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          {anim.effects.map((e: any, i: number) => (
            <div key={i} className="rounded-md border border-white/10 p-2">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <label><input type="checkbox" checked={e.enabled !== false} onChange={(ev) => setFx(i, { enabled: ev.target.checked })} /> <b>{e.id ?? e.type}</b></label>
                <Badge>{e.type}</Badge>
                <select aria-label="Mask" className={inputCls} value={e.mask ?? ""} onChange={(ev) => setFx(i, { mask: ev.target.value || null })}>
                  <option value="">full frame</option>{Object.keys(anim.masks ?? {}).concat(typeof e.mask === "string" && !anim.masks?.[e.mask] ? [e.mask] : []).map((m) => <option key={m}>{m}</option>)}</select>
                <label className="text-xs">intensity <input type="range" min={0} max={2} step={0.05} defaultValue={e.params?.intensity ?? 1}
                  onMouseUp={(ev) => setFx(i, { params: { ...e.params, intensity: +(ev.target as HTMLInputElement).value } })} /></label>
                <label className="text-xs">seed <input className={`${inputCls} w-16`} type="number" defaultValue={e.seed} onBlur={(ev) => setFx(i, { seed: +ev.target.value })} /></label>
                <Btn kind="danger" onClick={() => put(anim.effects.filter((_: any, j: number) => j !== i))}>Remove</Btn>
              </div>
              <details className="mt-1"><summary className="cursor-pointer text-xs text-atmo">parameters</summary>
                <JsonEdit rows={6} value={e.params ?? {}} onSave={(v) => setFx(i, { params: v })} /></details>
            </div>))}
          <div className="text-xs text-white/50">Loop length {p.data.render.loop_seconds} s. Changing effects after preview approval invalidates the approval.</div>
        </div>
        <div>
          <img alt="Animated frame preview" className="w-full rounded" src={`/api/projects/${p.id}/frame-preview?t=${t}&v=${bust}`} />
          <div className="mt-2 flex items-center gap-2 text-xs">frame at
            <input aria-label="Preview time" type="range" min={0} max={p.data.render.loop_seconds} step={0.5} value={t} onChange={(e) => setT(+e.target.value)} />{t}s
            <Btn onClick={() => setBust(Date.now())}>Refresh frame</Btn></div>
        </div>
      </div>
    </Card>
  );
}

function Audio({ p, stems, reload }: { p: any; stems: any[]; reload: () => void }) {
  const audio = p.data.audio;
  const [mute, setMute] = useState<Record<string, boolean>>({});
  const [solo, setSolo] = useState<string | null>(null);
  const players = useRef<Record<string, HTMLAudioElement | null>>({});
  const [f, setF] = useState<File | null>(null);
  const [lic, setLic] = useState({ name: "CC0-1.0", creator: "", source_url: "", title: "" });
  const put = async (layers: any[], extra: any = {}) => { await api.put(`/projects/${p.id}/config`, { audio: { ...audio, layers, ...extra } }); reload(); };
  const setL = (i: number, patch: any) => put(audio.layers.map((l: any, j: number) => (j === i ? { ...l, ...patch } : l)));
  useEffect(() => { Object.entries(players.current).forEach(([id, el]) => { if (el) el.muted = !!mute[id] || (solo !== null && solo !== id); }); }, [mute, solo]);
  const all = (fn: (a: HTMLAudioElement) => void) => Object.values(players.current).forEach((a) => a && fn(a));
  return (
    <Card title="4 · Soundscape (procedural synthesis + licensed recordings)" actions={<>
      <select aria-label="Add layer" className={inputCls} onChange={(e) => { if (e.target.value) put([...audio.layers, { id: `${e.target.value}_${audio.layers.length}`, type: e.target.value, gain_db: -18, seed: audio.layers.length + 11, params: {} }]); e.target.value = ""; }}>
        <option value="">+ add layer</option>{LAYER_TYPES.map((x) => <option key={x}>{x}</option>)}</select>
      <label className="text-xs">profile <select className={inputCls} value={audio.profile} onChange={(e) => put(audio.layers, { profile: e.target.value })}><option>sleep</option><option>focus</option></select></label>
      <label className="text-xs">mix seed <input className={`${inputCls} w-16`} type="number" defaultValue={audio.seed} onBlur={(e) => put(audio.layers, { seed: +e.target.value })} /></label></>}>
      <div className="overflow-x-auto"><table>
        <thead><tr><th>Layer</th><th>Type</th><th>Gain dB</th><th>Pan</th><th>Variation dB</th><th>HP / LP Hz</th><th>Seed</th><th>Render</th><th>Preview stem</th><th /></tr></thead>
        <tbody>{audio.layers.map((l: any, i: number) => {
          const stem = stems.find((s) => s.meta?.layer_id === l.id);
          return (
            <tr key={l.id}>
              <td>{l.id}</td><td><Badge>{l.type}</Badge></td>
              <td><input aria-label={`${l.id} gain`} type="range" min={-48} max={0} step={1} defaultValue={l.gain_db} onMouseUp={(e) => setL(i, { gain_db: +(e.target as HTMLInputElement).value })} /> {l.gain_db}</td>
              <td><input aria-label={`${l.id} pan`} type="range" min={-1} max={1} step={0.1} defaultValue={l.pan ?? 0} onMouseUp={(e) => setL(i, { pan: +(e.target as HTMLInputElement).value })} /></td>
              <td><input className={`${inputCls} w-14`} type="number" step={0.5} defaultValue={l.variation_db ?? 1.5} onBlur={(e) => setL(i, { variation_db: +e.target.value })} /></td>
              <td className="whitespace-nowrap"><input className={`${inputCls} w-16`} type="number" placeholder="hp" defaultValue={l.highpass_hz ?? ""} onBlur={(e) => setL(i, { highpass_hz: e.target.value ? +e.target.value : null })} />
                <input className={`${inputCls} w-16`} type="number" placeholder="lp" defaultValue={l.lowpass_hz ?? ""} onBlur={(e) => setL(i, { lowpass_hz: e.target.value ? +e.target.value : null })} /></td>
              <td><input className={`${inputCls} w-16`} type="number" defaultValue={l.seed} onBlur={(e) => setL(i, { seed: +e.target.value })} /></td>
              <td><label className="text-xs"><input type="checkbox" checked={!l.mute} onChange={(e) => setL(i, { mute: !e.target.checked })} /> in mix</label></td>
              <td className="whitespace-nowrap">{stem ? <>
                <audio ref={(el) => { players.current[l.id] = el; }} src={file(stem.path, stem.id)} preload="none" loop />
                <button className="mr-1 text-xs" onClick={() => setMute({ ...mute, [l.id]: !mute[l.id] })}><Badge tone={mute[l.id] ? "bad" : "dim"}>M</Badge></button>
                <button className="text-xs" onClick={() => setSolo(solo === l.id ? null : l.id)}><Badge tone={solo === l.id ? "warn" : "dim"}>S</Badge></button></> : <span className="text-xs text-white/30">build preview</span>}</td>
              <td><details><summary className="cursor-pointer text-xs text-atmo">params</summary><JsonEdit rows={4} value={l.params ?? {}} onSave={(v) => setL(i, { params: v })} /></details>
                <Btn kind="danger" onClick={() => put(audio.layers.filter((_: any, j: number) => j !== i))}>×</Btn></td>
            </tr>);
        })}</tbody></table></div>
      {stems.length > 0 && <div className="mt-2 flex gap-2"><Btn onClick={() => all((a) => { a.currentTime = 0; a.play(); })}>▶ Play stems together</Btn><Btn onClick={() => all((a) => a.pause())}>■ Stop</Btn>
        <span className="self-center text-xs text-white/50">Mute/solo here is for listening only. Use "in mix" and the sliders to change the actual mix.</span></div>}
      <div className="mt-4 grid gap-2 border-t border-white/10 pt-3 md:grid-cols-5">
        <Field label="Licensed recording (birds, fire crackle, streams…)"><input type="file" accept="audio/*" onChange={(e) => setF(e.target.files?.[0] ?? null)} className="text-sm" /></Field>
        <Field label="License"><select className={inputCls} value={lic.name} onChange={(e) => setLic({ ...lic, name: e.target.value })}>
          {["CC0-1.0", "CC-BY-4.0", "pixabay-content-license", "user-owned", "CC-BY-NC-4.0", "custom"].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Title / creator"><input className={inputCls} placeholder="title" value={lic.title} onChange={(e) => setLic({ ...lic, title: e.target.value })} />
          <input className={inputCls} placeholder="creator" value={lic.creator} onChange={(e) => setLic({ ...lic, creator: e.target.value })} /></Field>
        <Field label="Source URL"><input className={inputCls} value={lic.source_url} onChange={(e) => setLic({ ...lic, source_url: e.target.value })} /></Field>
        <div className="self-end"><Btn disabled={!f} onClick={async () => {
          const fd = new FormData(); fd.append("file", f!); fd.append("license", JSON.stringify({ ...lic, source: lic.source_url })); fd.append("layer_id", (f!.name.split(".")[0] || "recording").slice(0, 30));
          const r = await api.post(`/projects/${p.id}/audio/import`, fd);
          if (!r.evaluation.ok) alert("Imported, but publication is blocked until rights are clear: " + r.evaluation.issues.join("; "));
          reload();
        }}>Import as looping layer</Btn></div>
      </div>
    </Card>
  );
}

function PreviewStage({ p, reload }: { p: any; reload: () => void }) {
  const prev = p.assets.filter((a: any) => a.kind === "preview").at(-1);
  const mix = p.assets.filter((a: any) => a.kind === "audio_mix").at(-1);
  const loop = p.data.loop_check;
  const stale = prev && p.data.preview_hash && p.state !== "PREVIEW_READY" && !p.preview_approved;
  return (
    <Card title="5 · Representative preview" actions={<>
      <Btn onClick={() => api.post(`/projects/${p.id}/preview`, { parts: ["visual", "audio"] }).then(reload)}>Build preview (60 s)</Btn>
      <Btn onClick={() => api.post(`/projects/${p.id}/preview`, { parts: ["audio"] }).then(reload)}>Rebuild audio only</Btn>
      <Btn onClick={() => api.post(`/projects/${p.id}/preview`, { parts: ["visual"] }).then(reload)}>Rebuild visuals only</Btn>
      <Btn onClick={() => api.post(`/projects/${p.id}/preview`, { parts: ["audio"], seconds: 600 }).then(reload)} title="Check variation and loop points">Long audio check (10 min)</Btn>
      {p.state === "PREVIEW_READY" && <Btn kind="primary" onClick={() => api.post(`/projects/${p.id}/preview/approve`).then(reload)}>Approve preview</Btn>}</>}>
      {prev ? <div className="grid gap-3 lg:grid-cols-3">
        <video key={prev.id} controls loop className="w-full rounded lg:col-span-2" src={file(prev.path, prev.id)} />
        <div className="flex flex-col gap-2 text-sm">
          {p.preview_approved ? <Badge tone="ok">approved for this configuration</Badge> : stale ? <Badge tone="warn">configuration changed: rebuild</Badge> : <Badge tone="warn">awaiting approval</Badge>}
          {loop && <div>Loop boundary: <Badge tone={loop.seamless ? "ok" : "bad"}>{loop.seamless ? "seamless" : "visible jump"}</Badge>
            <div className="text-xs text-white/50">jump {loop.boundary_diff} vs typical {loop.typical_diff} (ratio {loop.ratio})</div></div>}
          {mix?.meta?.loudness && <div>Preview loudness: {mix.meta.loudness.integrated_lufs} LUFS · peak {mix.meta.loudness.true_peak_db} dBTP<div className="text-xs text-white/50">master gain {mix.meta.gain_db} dB (seeded, reproduced exactly in the final render)</div></div>}
          {mix && <audio controls src={file(mix.path, mix.id)} className="w-full" />}
        </div>
      </div> : <p className="text-sm text-white/50">Build a preview to hear and see the scene. The full render is locked until a preview is approved.</p>}
    </Card>
  );
}

function RenderStage({ p, reload }: { p: any; reload: () => void }) {
  const [dur, setDur] = useState(p.data.render.duration_hours * 3600);
  const est = p.estimated_output_bytes ? p.estimated_output_bytes * dur / (p.data.render.duration_hours * 3600) : null;
  const final = p.assets.find((a: any) => a.kind === "final_video" && a.role === "selected");
  return (
    <Card title="6 · Full render" actions={<>
      <select aria-label="Duration" className={inputCls} value={dur} onChange={(e) => setDur(+e.target.value)}>
        {DURATIONS.map(([l, s]) => <option key={s} value={s}>{l}</option>)}</select>
      <Btn kind="primary" onClick={() => confirmThen(`Start a ${(dur / 3600).toFixed(2)} h render? Estimated size ${fmtBytes(est)}.`, () => api.post(`/projects/${p.id}/render`, { duration_s: dur }).then(reload))}>Render</Btn></>}>
      <div className="text-sm">Estimated output: {fmtBytes(est)} · free disk: {fmtBytes(p.disk_free_bytes)} {est && p.disk_free_bytes < est * 1.2 && <Badge tone="bad">not enough space</Badge>}</div>
      <p className="text-xs text-white/50">The approved visual master is looped by stream copy (no re-encode); audio is synthesized in 1 s chunks and streamed to the encoder, so memory use stays flat for 8 h videos.</p>
      {final && <div className="mt-2 text-sm">Final: {final.path} ({fmtBytes(final.size_bytes)}, {(final.duration_s / 3600).toFixed(2)} h, rendered in {final.meta.render_seconds}s)</div>}
    </Card>
  );
}

function QaList({ title, r }: { title: string; r: any }) {
  return (
    <div><div className="mb-1 text-sm font-medium">{title} <Badge tone={r.status === "pass" ? "ok" : r.status === "warn" ? "warn" : "bad"}>{r.status}</Badge></div>
      <ul className="text-xs">
        {r.errors.map((c: any, i: number) => <li key={"e" + i} className="text-rose-300">✗ {c.check} {c.detail && <span className="text-white/40">{JSON.stringify(c.detail)}</span>}</li>)}
        {r.warnings.map((c: any, i: number) => <li key={"w" + i} className="text-amber-200">! {c.check} {c.detail && <span className="text-white/40">{JSON.stringify(c.detail)}</span>}</li>)}
        {r.passed.map((c: any, i: number) => <li key={"p" + i} className="text-emerald-300/80">✓ {c.check}</li>)}
      </ul></div>
  );
}

function Review({ p, thumbs, reload }: { p: any; thumbs: any[]; reload: () => void }) {
  const d = p.data;
  const [meta, setMeta] = useState(d.metadata);
  useEffect(() => setMeta(d.metadata), [d.metadata?.title]);
  const final = p.assets.find((a: any) => a.kind === "final_video" && a.role === "selected");
  return (
    <>
      <Card title="7 · Quality assurance">
        <div className="grid gap-4 md:grid-cols-2"><QaList title="Technical" r={d.qa_technical} />{d.qa_creative && <QaList title="Creative & rights" r={d.qa_creative} />}</div>
        {final && final.duration_s <= 600 && <video controls className="mt-3 w-full max-w-xl rounded" src={file(final.path, final.id)} />}
      </Card>
      <Card title="8 · Thumbnail">
        <div className="grid gap-3 md:grid-cols-3">
          {thumbs.map((t) => (
            <figure key={t.id} className={`rounded-lg border p-1 ${t.role === "selected" ? "border-gold" : "border-white/10"}`}>
              <img alt={t.meta?.note} src={file(t.path, t.id)} className="w-full rounded" />
              <div className="mt-1 flex items-center gap-2">
                <img alt="small size preview" src={file(t.path.replace(".jpg", "_small.jpg"), t.id)} className="w-24 rounded" />
                <img alt="tiny size preview" src={file(t.path.replace(".jpg", "_small.jpg"), t.id)} className="w-12 rounded" />
                {t.role === "selected" ? <Badge tone="ok">selected</Badge> : <Btn onClick={() => api.post(`/projects/${p.id}/thumbnails/${t.id}/select`).then(reload)}>Select</Btn>}
              </div>
              <figcaption className="text-[11px] text-white/50">{t.meta?.note} · {fmtBytes(t.size_bytes)}</figcaption>
            </figure>))}
        </div>
        <p className="mt-2 text-xs text-white/40">No A/B results exist yet; selection is your judgment.</p>
      </Card>
      <Card title="9 · Metadata (SEO)" actions={<Btn onClick={async () => { const r = await api.put(`/projects/${p.id}/metadata`, meta); setMeta(r.metadata); reload(); }}>Save</Btn>}>
        {meta && <div className="grid gap-3 lg:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Field label={`Title (${meta.title.length}/100)`}><input className={inputCls} value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></Field>
            <div className="flex flex-col gap-1 text-xs">{meta.title_candidates.map((t: string) => <button key={t} className="text-left text-atmo hover:text-gold" onClick={() => setMeta({ ...meta, title: t })}>↳ {t}</button>)}</div>
            <Field label="Tags (comma separated)"><input className={inputCls} value={meta.tags.join(", ")} onChange={(e) => setMeta({ ...meta, tags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></Field>
            <div className="text-xs">Playlist: {meta.playlist ?? "–"} · category {meta.category_id} · language {meta.language}</div>
            <div className="text-xs">Disclosure: {meta.synthetic_disclosure?.reason} {meta.synthetic_disclosure?.contains_synthetic_media_flag && <Badge tone="warn">altered/synthetic flag recommended</Badge>}</div>
          </div>
          <Field label="Description"><textarea className={`${inputCls} font-mono text-xs`} rows={14} value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} /></Field>
        </div>}
        {d.metadata_errors?.length > 0 && <ul className="mt-2 text-xs text-rose-300">{d.metadata_errors.map((e: string) => <li key={e}>{e}</li>)}</ul>}
      </Card>
      <Card title="10 · Approve, export & publish">
        <div className="flex flex-wrap gap-2">
          {p.state === "FINAL_REVIEW" && <Btn kind="primary" onClick={() => api.post(`/projects/${p.id}/approve-final`).then(reload)}>Approve final content</Btn>}
          {["APPROVED", "READY_FOR_UPLOAD", "UPLOADED_PRIVATE", "PUBLISHED", "SCHEDULED"].includes(p.state) && <Btn onClick={async () => { const r = await api.post(`/projects/${p.id}/export`); alert(`Package written to workspace/${r.export_dir}`); reload(); }}>Export YouTube upload package</Btn>}
          {p.state === "READY_FOR_UPLOAD" && <Btn kind="primary" onClick={() => confirmThen("Upload as PRIVATE to the configured channel?", () => api.post(`/projects/${p.id}/upload`).then(reload))}>Upload privately</Btn>}
          {p.state === "UPLOADED_PRIVATE" && <PublishControls p={p} reload={reload} />}
        </div>
        {d.export_dir && <p className="mt-2 text-xs text-white/50">Package: workspace/{d.export_dir} (MP4, thumbnail, title, description, tags, manifest, CHECKLIST.md)</p>}
        {d.youtube_video_id && <p className="mt-1 text-sm">YouTube video: {d.youtube_video_id}</p>}
      </Card>
    </>
  );
}

function PublishControls({ p, reload }: { p: any; reload: () => void }) {
  const [at, setAt] = useState("");
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Btn kind="danger" onClick={() => confirmThen("Make this video PUBLIC now?", () => api.post(`/projects/${p.id}/publish`, { mode: "public", confirm: true }).then(reload))}>Publish publicly</Btn>
      <Field label="or schedule (local time)"><input type="datetime-local" className={inputCls} value={at} onChange={(e) => setAt(e.target.value)} /></Field>
      <Btn disabled={!at} onClick={() => confirmThen(`Schedule publication for ${at}?`, () => api.post(`/projects/${p.id}/publish`, { mode: "schedule", publish_at: new Date(at).toISOString(), confirm: true }).then(reload))}>Schedule</Btn>
    </div>
  );
}

function Provenance({ p }: { p: any }) {
  const [open, setOpen] = useState(false);
  return (
    <Card title="Provenance, approvals & history" actions={<><Btn onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</Btn><a className="self-center text-sm text-gold hover:underline" href={`/api/projects/${p.id}/manifest`} target="_blank" rel="noreferrer">Manifest JSON</a></>}>
      {open && <div className="grid gap-4 xl:grid-cols-2">
        <div className="overflow-x-auto"><table><thead><tr><th>Asset</th><th>Role</th><th>Provider / model</th><th>License</th><th>SHA-256</th><th>Cost</th></tr></thead><tbody>
          {p.assets.map((a: any) => <tr key={a.id}><td>{a.kind} #{a.id}</td><td>{a.role}</td><td>{a.provider} {a.model && <span className="text-white/40">/ {a.model}</span>}</td>
            <td>{a.license?.name ?? (a.provider === "synth" || a.provider === "driftbound" ? "original" : "–")}</td><td className="font-mono text-[10px]">{a.sha256?.slice(0, 12)}</td><td>{eur(a.cost_eur)}</td></tr>)}
        </tbody></table></div>
        <div>
          <table><thead><tr><th>Approval</th><th>Decision</th><th>Valid</th><th>When</th></tr></thead><tbody>
            {p.approvals.map((a: any) => <tr key={a.id}><td>{a.stage}</td><td>{a.decision}</td><td>{a.valid ? "yes" : <span className="text-white/40">no</span>}</td><td className="text-white/50">{new Date(a.at).toLocaleString()} {a.note}</td></tr>)}
          </tbody></table>
          <table className="mt-3"><thead><tr><th>Transition</th><th>By</th><th>Note</th></tr></thead><tbody>
            {p.transitions.map((t: any) => <tr key={t.id}><td>{t.from_state} → {t.to_state}</td><td>{t.actor}</td><td className="text-white/50">{t.note}</td></tr>)}
          </tbody></table>
        </div>
      </div>}
    </Card>
  );
}
