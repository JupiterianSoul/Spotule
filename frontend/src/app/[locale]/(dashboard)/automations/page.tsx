"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/ui/Page";
import { Toggle } from "@/components/ui/Toggle";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Automation } from "@/lib/types";

const KINDS = ["backup_discover_weekly", "backup_release_radar", "liked_songs_snapshot", "weekly_report", "auto_purge", "playlist_archive_monthly", "sync_playlists"] as const;
const DEFAULT_CRON: Record<string, string> = { backup_discover_weekly: "0 6 * * 1", backup_release_radar: "0 6 * * 5", weekly_report: "0 8 * * 1", liked_songs_snapshot: "0 3 * * 0", auto_purge: "0 4 * * *", playlist_archive_monthly: "0 5 1 * *", sync_playlists: "0 */6 * * *" };
const TAKES_PLAYLIST = new Set(["backup_discover_weekly", "backup_release_radar"]);
const CRON_RE = /^(\S+\s+){4}\S+$/;

export default function AutomationsPage() {
  const t = useTranslations("automations");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const jobs = useApi<Automation[]>(["automations"], "/api/v1/automations");
  const [editing, setEditing] = useState<string | null>(null);
  const [cron, setCron] = useState("");
  const [playlistId, setPlaylistId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const upsert = useMutation({
    mutationFn: ({ existing, kind, enabled, cron, config }: { existing?: Automation; kind: string; enabled: boolean; cron?: string; config?: Record<string, unknown> }) =>
      existing
        ? api(`/api/v1/automations/${existing.id}`, { method: "PATCH", body: { kind, cron: cron ?? existing.cron, enabled, config: config ?? existing.config } })
        : api("/api/v1/automations", { method: "POST", body: { kind, cron: cron ?? DEFAULT_CRON[kind], enabled, config: config ?? {} } }),
    onSuccess: () => { setEditing(null); setError(null); qc.invalidateQueries({ queryKey: ["automations"] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : tc("error")),
  });

  const startEdit = (kind: string, existing?: Automation) => {
    setEditing(kind);
    setCron(existing?.cron ?? DEFAULT_CRON[kind]);
    setPlaylistId(String(existing?.config?.playlist_id ?? ""));
  };
  const save = (kind: string, existing?: Automation) => {
    if (!CRON_RE.test(cron.trim())) { setError(t("invalidCron")); return; }
    const config = { ...(existing?.config ?? {}) };
    if (playlistId.trim()) config.playlist_id = playlistId.trim(); else delete config.playlist_id;
    upsert.mutate({ existing, kind, enabled: existing?.enabled ?? true, cron: cron.trim(), config });
  };

  return (
    <Page title={t("title")} subtitle={t("subtitle")}>
      {error && <p className="rounded-md bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
      <section className="card divide-y divide-border">
        {KINDS.map((kind) => {
          const existing = jobs.data?.find((j) => j.kind === kind);
          const open = editing === kind;
          return (
            <div key={kind} className="py-1">
              <Toggle label={t(`kinds.${kind}`)} checked={!!existing?.enabled} onChange={(v) => upsert.mutate({ existing, kind, enabled: v })} />
              <div className="flex flex-wrap items-center gap-3 pb-2 text-xs text-fg-subtle">
                <span>{t("schedule")}: <code>{existing?.cron ?? DEFAULT_CRON[kind]}</code></span>
                {existing?.next_run_at && <span>{t("nextRun")}: {new Date(existing.next_run_at).toLocaleString()}</span>}
                {existing?.last_run_at && <span>{t("lastRun")}: {new Date(existing.last_run_at).toLocaleString()}</span>}
                <button className="text-fg-muted underline" onClick={() => (open ? setEditing(null) : startEdit(kind, existing))}>{open ? tc("cancel") : t("edit")}</button>
              </div>
              {open && (
                <form className="mb-3 grid gap-2 rounded-md bg-surface/50 p-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save(kind, existing); }}>
                  <label className="text-xs"><span className="text-fg-muted">{t("cron")}</span>
                    <input className="input mt-1 font-mono" value={cron} onChange={(e) => setCron(e.target.value)} />
                  </label>
                  {TAKES_PLAYLIST.has(kind) && (
                    <label className="text-xs"><span className="text-fg-muted">{t("playlistId")}</span>
                      <input className="input mt-1 font-mono" value={playlistId} onChange={(e) => setPlaylistId(e.target.value)} placeholder="37i9dQZEVX…" />
                      <span className="mt-1 block text-fg-subtle">{t("playlistHint")}</span>
                    </label>
                  )}
                  <div className="sm:col-span-2"><button className="btn-primary py-1" disabled={upsert.isPending}>{tc("save")}</button></div>
                </form>
              )}
            </div>
          );
        })}
      </section>
    </Page>
  );
}
