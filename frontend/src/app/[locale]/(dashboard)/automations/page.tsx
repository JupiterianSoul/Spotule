"use client";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/ui/Page";
import { Toggle } from "@/components/ui/Toggle";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Automation } from "@/lib/types";

const KINDS = ["backup_discover_weekly", "backup_release_radar", "weekly_report", "liked_songs_snapshot", "auto_purge", "playlist_archive_monthly", "sync_playlists"] as const;
const DEFAULT_CRON: Record<string, string> = { backup_discover_weekly: "0 6 * * 1", backup_release_radar: "0 6 * * 5", weekly_report: "0 8 * * 1", liked_songs_snapshot: "0 3 * * 0", auto_purge: "0 4 * * *", playlist_archive_monthly: "0 5 1 * *", sync_playlists: "0 */6 * * *" };

export default function AutomationsPage() {
  const t = useTranslations("automations");
  const qc = useQueryClient();
  const jobs = useApi<Automation[]>(["automations"], "/api/v1/automations");
  const upsert = useMutation({
    mutationFn: ({ existing, kind, enabled }: { existing?: Automation; kind: string; enabled: boolean }) =>
      existing ? api(`/api/v1/automations/${existing.id}`, { method: "PATCH", body: { kind, cron: existing.cron, enabled, config: existing.config } })
               : api("/api/v1/automations", { method: "POST", body: { kind, cron: DEFAULT_CRON[kind], enabled, config: {} } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automations"] }),
  });
  return (
    <Page title={t("title")} subtitle={t("subtitle")}>
      <section className="card divide-y divide-border">
        {KINDS.map((kind) => {
          const existing = jobs.data?.find((j) => j.kind === kind);
          return (
            <div key={kind} className="py-1">
              <Toggle label={t(`kinds.${kind}`)} checked={!!existing?.enabled} onChange={(v) => upsert.mutate({ existing, kind, enabled: v })} />
              {existing && <p className="pb-2 text-xs text-fg-subtle">{t("schedule")}: <code>{existing.cron}</code>{existing.next_run_at && ` · ${t("nextRun")}: ${new Date(existing.next_run_at).toLocaleString()}`}</p>}
            </div>
          );
        })}
      </section>
    </Page>
  );
}
