"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { X } from "lucide-react";
import type { ToolSpec } from "@/lib/types";

/**
 * Generic form generated from the tool's Pydantic JSON schema. Handles the primitive
 * shapes our tools use (string, number, boolean, string[] as one-per-line, enums);
 * a tool needing a richer UI registers a custom component in `features/tools/custom/`.
 */
type Prop = { type?: string | string[]; title?: string; description?: string; default?: unknown; enum?: string[]; items?: { type?: string }; anyOf?: { type?: string; enum?: string[] }[] };

export function ToolRunner({ spec, pending, onClose, onRun }: { spec: ToolSpec; pending: boolean; onClose: () => void; onRun: (params: Record<string, unknown>) => void }) {
  const t = useTranslations("common");
  const schema = spec.params_schema as { properties?: Record<string, Prop>; required?: string[] };
  const props = schema.properties ?? {};
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(Object.entries(props).map(([k, p]) => [k, p.default ?? (kind(p) === "boolean" ? false : "")])));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const out: Record<string, unknown> = {};
    for (const [k, p] of Object.entries(props)) {
      const v = values[k];
      const kd = kind(p);
      if (v === "" || v === undefined || v === null) continue;
      out[k] = kd === "array" ? String(v).split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
             : kd === "number" ? Number(v) : v;
    }
    onRun(out);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <form onClick={(e) => e.stopPropagation()} onSubmit={submit}
            className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-bg-elevated p-5 sm:rounded-2xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div><h2 className="text-lg font-bold">{spec.title}</h2><p className="text-sm text-fg-muted">{spec.description}</p></div>
          <button type="button" onClick={onClose} className="btn-ghost p-1.5" aria-label={t("close")}><X className="h-4 w-4" /></button>
        </div>
        <div className="space-y-3">
          {Object.entries(props).map(([k, p]) => {
            const kd = kind(p);
            const label = p.title ?? k;
            const enumVals = p.enum ?? p.anyOf?.find((a) => a.enum)?.enum;
            return (
              <label key={k} className="block text-sm">
                <span className="mb-1 block text-fg-muted">{label}{schema.required?.includes(k) && " *"}</span>
                {kd === "boolean" ? (
                  <input type="checkbox" checked={!!values[k]} onChange={(e) => setValues({ ...values, [k]: e.target.checked })} className="h-4 w-4 accent-accent" />
                ) : enumVals ? (
                  <select className="input" value={String(values[k] ?? "")} onChange={(e) => setValues({ ...values, [k]: e.target.value })}>
                    <option value="">—</option>{enumVals.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                ) : kd === "array" || k === "text" ? (
                  <textarea className="input min-h-24 font-mono text-xs" value={String(values[k] ?? "")} onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
                ) : (
                  <input className="input" type={kd === "number" ? "number" : "text"} step="any" value={String(values[k] ?? "")}
                         onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
                )}
                {p.description && <span className="mt-1 block text-xs text-fg-subtle">{p.description}</span>}
              </label>
            );
          })}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost">{t("cancel")}</button>
          <button type="submit" disabled={pending} className={spec.destructive ? "btn-danger" : "btn-primary"}>{t("run")}</button>
        </div>
      </form>
    </div>
  );
}

function kind(p: Prop): string {
  const raw = p.type ?? p.anyOf?.map((a) => a.type).find((x) => x && x !== "null");
  const ty = Array.isArray(raw) ? raw.find((x) => x !== "null") : raw;
  if (ty === "integer") return "number";
  return ty ?? "string";
}
