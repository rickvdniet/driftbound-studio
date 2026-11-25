import { ReactNode, useState } from "react";
import { api } from "../services/api";

export const Card = ({ title, children, actions, className = "" }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) => (
  <section className={`min-w-0 overflow-x-auto rounded-xl border border-white/10 bg-navy-800/70 p-4 ${className}`}>
    {(title || actions) && (
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        {title && <h2 className="text-sm font-semibold tracking-wide text-gold">{title}</h2>}
        <div className="flex flex-wrap gap-2">{actions}</div>
      </div>
    )}
    {children}
  </section>
);

export const Stat = ({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) => (
  <div className="rounded-lg border border-white/10 bg-navy-900/60 p-3">
    <div className="text-xs text-atmo">{label}</div>
    <div className="mt-1 text-xl font-semibold text-ivory">{value ?? <span className="text-sm text-white/40">no data</span>}</div>
    {hint && <div className="mt-1 text-[11px] text-white/40">{hint}</div>}
  </div>
);

const tones: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-300 border-emerald-400/30",
  warn: "bg-amber-500/15 text-amber-200 border-amber-400/30",
  bad: "bg-rose-500/15 text-rose-300 border-rose-400/30",
  info: "bg-sky-500/10 text-sky-200 border-sky-400/30",
  dim: "bg-white/5 text-white/60 border-white/10",
};
export const Badge = ({ children, tone = "dim" }: { children: ReactNode; tone?: keyof typeof tones | string }) => (
  <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] ${tones[tone] ?? tones.dim}`}>{children}</span>
);

/** Button that runs an async action, shows a busy state and surfaces errors. */
export function Btn({ onClick, children, kind = "default", disabled, title }: {
  onClick: () => Promise<unknown> | unknown; children: ReactNode; kind?: "default" | "primary" | "danger"; disabled?: boolean; title?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const cls = {
    default: "border-white/15 bg-white/5 hover:bg-white/10 text-ivory",
    primary: "border-gold/40 bg-gold/15 hover:bg-gold/25 text-gold",
    danger: "border-rose-400/40 bg-rose-500/10 hover:bg-rose-500/20 text-rose-200",
  }[kind];
  return (
    <span className="inline-flex flex-col">
      <button title={title} disabled={disabled || busy}
        className={`rounded-md border px-3 py-1.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-40 ${cls}`}
        onClick={async () => { setBusy(true); setErr(null); try { await onClick(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } }}>
        {busy ? "Working…" : children}
      </button>
      {err && <span role="alert" className="mt-1 max-w-xs text-xs text-rose-300">{err}</span>}
    </span>
  );
}

export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <label className="flex flex-col gap-1 text-xs text-atmo">{label}{children}</label>
);

export const inputCls = "rounded-md border border-white/15 bg-navy-900 px-2 py-1.5 text-sm text-ivory focus:border-gold focus:outline-none";

export const Loading = ({ error }: { error?: string | null }) =>
  error ? <div role="alert" className="text-rose-300">{error}</div> : <div className="animate-pulse text-white/40">Loading…</div>;

export const Progress = ({ value, label }: { value: number; label?: string }) => (
  <div>
    <div className="h-2 overflow-hidden rounded bg-white/10" role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-gold transition-all" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
    {label && <div className="mt-1 text-xs text-white/50">{label}</div>}
  </div>
);

/** JSON editor with validation; calls onSave with the parsed value. */
export function JsonEdit({ value, onSave, rows = 10 }: { value: unknown; onSave: (v: any) => Promise<unknown>; rows?: number }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <textarea aria-label="JSON" className={`${inputCls} font-mono text-xs`} rows={rows} value={text} onChange={(e) => setText(e.target.value)} />
      {err && <div className="text-xs text-rose-300">{err}</div>}
      <div><Btn onClick={async () => { try { await onSave(JSON.parse(text)); setErr(null); } catch (e) { setErr((e as Error).message); } }}>Save</Btn></div>
    </div>
  );
}

export const fmtBytes = (b?: number | null) => b == null ? "–" : b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(0)} kB`;
export const fmtNum = (n?: number | null, d = 0) => n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: d });
export const eur = (n?: number | null) => n == null ? "–" : `€${n.toFixed(2)}`;
export const stateTone = (s: string) => ["PUBLISHED", "APPROVED", "UPLOADED_PRIVATE", "SCHEDULED"].includes(s) ? "ok"
  : ["IMAGE_REVIEW", "PREVIEW_READY", "FINAL_REVIEW"].includes(s) ? "warn" : ["FAILED", "CANCELLED"].includes(s) ? "bad" : "info";

export async function confirmThen(msg: string, fn: () => Promise<unknown>) {
  if (window.confirm(msg)) return fn();
}
export { api };
