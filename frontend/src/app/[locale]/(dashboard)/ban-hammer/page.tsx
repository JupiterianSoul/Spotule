"use client";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Zap } from "lucide-react";
import { Page } from "@/components/ui/Page";
import { Toggle } from "@/components/ui/Toggle";
import { api, ApiError } from "@/lib/api";
import { useApi, useMe } from "@/lib/hooks";
import type { BannedGenre, PurgeStatus, SkipEvent } from "@/lib/types";

export default function BanHammerPage() {
  const t = useTranslations("banhammer");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const rules = useApi<BannedGenre[]>(["banned-genres"], "/api/v1/banhammer/genres");
  const skips = useApi<SkipEvent[]>(["skip-events"], "/api/v1/banhammer/guard/events", { limit: 20 });
  const [pattern, setPattern] = useState("");
  const [mode, setMode] = useState<BannedGenre["match_mode"]>("contains");
  const [error, setError] = useState<string | null>(null);
  const [purgeRun, setPurgeRun] = useState<string | null>(null);
  const purge = useApi<PurgeStatus>(["purge", purgeRun], `/api/v1/banhammer/purge/${purgeRun}`, undefined, !!purgeRun);

  const addRule = useMutation({
    mutationFn: () => api("/api/v1/banhammer/genres", { method: "POST", locale, body: { pattern, match_mode: mode } }),
    onSuccess: () => { setPattern(""); setError(null); qc.invalidateQueries({ queryKey: ["banned-genres"] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : tc("error")),
  });
  const removeRule = useMutation({
    mutationFn: (id: string) => api(`/api/v1/banhammer/genres/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["banned-genres"] }),
  });
  const toggleGuard = useMutation({
    mutationFn: (enabled: boolean) => api("/api/v1/banhammer/guard/toggle", { method: "POST", locale, query: { enabled } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
    onError: (e) => setError(e instanceof ApiError ? e.message : tc("error")),
  });
  const startPurge = useMutation({
    mutationFn: (dry_run: boolean) => api<{ run_id: string }>("/api/v1/banhammer/purge", { method: "POST", locale, body: { target: "liked_songs", dry_run } }),
    onSuccess: (r) => setPurgeRun(r.run_id),
  });

  return (
    <Page title={t("title")} subtitle={t("subtitle")}>
      {error && <p className="rounded-md bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
      <section className="card">
        <h2 className="mb-3 font-semibold">{t("registry")}</h2>
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (pattern.trim()) addRule.mutate(); }}>
          <input className="input flex-1" value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder={t("patternHint")} aria-label={t("pattern")} />
          <select className="input sm:w-40" value={mode} onChange={(e) => setMode(e.target.value as BannedGenre["match_mode"])} aria-label={t("matchMode")}>
            {(["contains", "exact", "regex"] as const).map((m) => <option key={m} value={m}>{t(`modes.${m}`)}</option>)}
          </select>
          <button className="btn-primary" disabled={addRule.isPending}>{t("addRule")}</button>
        </form>
        <ul className="mt-4 divide-y divide-border">
          {rules.data?.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
              <code className="rounded bg-surface px-2 py-0.5">{r.pattern}</code>
              <span className="chip">{t(`modes.${r.match_mode}`)}</span>
              <span className="ml-auto hidden text-xs text-fg-subtle sm:inline">
                {r.apply_skip_guard && t("applySkip")} {r.apply_skip_guard && r.apply_library_purge && "·"} {r.apply_library_purge && t("applyPurge")}
              </span>
              <button onClick={() => removeRule.mutate(r.id)} className="btn-ghost p-1.5" aria-label={tc("delete")}><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card">
          <h2 className="font-semibold">{t("guard.title")}</h2>
          <p className="mb-2 text-sm text-fg-muted">{t("guard.subtitle")}</p>
          <Toggle label={t("guard.enable")} checked={!!me?.preferences.skip_guard_enabled}
                  disabled={me?.user.product !== "premium"} onChange={(v) => toggleGuard.mutate(v)} />
          {me?.user.product !== "premium" && <p className="text-xs text-warning">{t("guard.premiumRequired")}</p>}
          <h3 className="mt-4 mb-2 text-sm font-semibold">{t("guard.recentSkips")}</h3>
          {!skips.data?.length && <p className="text-sm text-fg-subtle">{t("guard.noSkips")}</p>}
          <ul className="space-y-1 text-sm">
            {skips.data?.map((s) => (
              <li key={s.id} className="flex items-center gap-2">
                <Zap className={`h-3.5 w-3.5 ${s.success ? "text-accent" : "text-danger"}`} />
                <span className="flex-1 truncate">{s.track_name} <span className="text-fg-subtle">· {s.matched_genre}</span></span>
                <span className="text-xs tabular-nums text-fg-muted">{s.latency_ms != null && t("guard.latency", { ms: s.latency_ms })}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <h2 className="font-semibold">{t("purge.title")}</h2>
          <p className="mb-3 text-sm text-fg-muted">{t("purge.subtitle")}</p>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost border border-border" onClick={() => startPurge.mutate(true)}>{t("purge.scan")}</button>
            {purge.data?.status === "succeeded" && purge.data.dry_run && purge.data.matched > 0 && (
              <button className="btn-danger" onClick={() => startPurge.mutate(false)}>{t("purge.execute", { count: purge.data.matched })}</button>
            )}
          </div>
          {purge.data && (
            <div className="mt-4 text-sm">
              <p className="text-fg-muted">
                {t(`purge.status.${purge.data.status as "queued" | "running" | "succeeded" | "failed"}`)} · {t("purge.scanned")} {purge.data.scanned} · {t("purge.matched")} {purge.data.matched} · {t("purge.removed")} {purge.data.removed}
              </p>
              <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto">
                {purge.data.report.slice(0, 200).map((r) => (
                  <li key={r.track_id} className="truncate text-xs"><span className="text-fg">{r.name}</span> <span className="text-fg-subtle">— {r.artist} · {r.genre}</span></li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
    </Page>
  );
}
