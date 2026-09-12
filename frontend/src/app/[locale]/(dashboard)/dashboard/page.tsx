"use client";
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { AlertTriangle } from "lucide-react";
import { Page } from "@/components/ui/Page";
import { StatTile } from "@/components/widgets/StatTile";
import { TopList } from "@/components/widgets/TopList";
import { ListeningClock } from "@/components/widgets/ListeningClock";
import { MilestoneList } from "@/components/widgets/MilestoneList";
import { TimeframePicker } from "@/components/widgets/TimeframePicker";
import { useApi, useMe, tfQuery, type Timeframe } from "@/lib/hooks";
import type { Clock, Milestone, Overview, TopArtist, TopGenre, TopTrack } from "@/lib/types";
import { fmtMinutes } from "@/lib/utils";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const [tf, setTf] = useState<Timeframe>({ preset: "4w" });
  const q = tfQuery(tf);
  const { data: me } = useMe();
  const overview = useApi<Overview>(["overview"], "/api/v1/stats/overview", q);
  const tracks = useApi<TopTrack[]>(["top", "tracks"], "/api/v1/stats/top/tracks", { ...q, limit: 5 });
  const artists = useApi<TopArtist[]>(["top", "artists"], "/api/v1/stats/top/artists", { ...q, limit: 5 });
  const genres = useApi<TopGenre[]>(["top", "genres"], "/api/v1/stats/top/genres", { ...q, limit: 8 });
  const clock = useApi<Clock>(["clock"], "/api/v1/stats/clock", q);
  const milestones = useApi<Milestone[]>(["milestones"], "/api/v1/stats/milestones", { limit: 5 });
  const tm = useTranslations("milestones");
  const qc = useQueryClient();
  const newCount = milestones.data?.filter((m) => m.new).length ?? 0;
  useEffect(() => {
    // Show the badge once, then tell the server so it does not reappear on the next visit.
    if (newCount > 0) api("/api/v1/stats/milestones/seen", { method: "POST" }).then(() => qc.invalidateQueries({ queryKey: ["milestones"] })).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newCount]);

  return (
    <Page title={t("title")}>
      {me && !me.preferences.stream_logger_enabled && (
        // Silent data loss otherwise: Spotify only keeps the last 50 plays, so every hour
        // this stays off is history that can never be recovered.
        <div className="flex flex-wrap items-center gap-3 rounded-card border border-warning/40 bg-warning/10 px-4 py-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-warning" />
          <p className="flex-1 text-sm text-warning">{t("loggerOff")}</p>
          <Link href="/settings" className="btn-primary py-1">{t("loggerOffCta")}</Link>
        </div>
      )}
      <TimeframePicker value={tf} onChange={setTf} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label={t("minutesListened")} value={fmtMinutes(locale, overview.data?.minutes ?? 0)} loading={overview.isLoading} />
        <StatTile label={t("streams")} value={fmtMinutes(locale, overview.data?.streams ?? 0)} loading={overview.isLoading} />
        <StatTile label={t("uniqueTracks")} value={fmtMinutes(locale, overview.data?.unique_tracks ?? 0)} loading={overview.isLoading} />
        <StatTile label={t("uniqueArtists")} value={fmtMinutes(locale, overview.data?.unique_artists ?? 0)} loading={overview.isLoading} />
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="chip">{t("guardStatus")}: {me?.preferences.skip_guard_enabled ? t("guardOn") : t("guardOff")}</span>
        <span className="chip">{t("loggerStatus")}: {me?.preferences.stream_logger_enabled ? t("guardOn") : t("guardOff")}</span>
        {newCount > 0 && <span className="chip bg-warning/20 text-warning">🏆 {tm("new", { count: newCount })}</span>}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <TopList title={t("topTracks")} loading={tracks.isLoading}
                 rows={tracks.data?.map((r) => ({ id: r.id, name: r.name, subtitle: r.album, image_url: r.image_url, streams: r.streams, minutes: r.minutes }))} />
        <TopList title={t("topArtists")} square={false} loading={artists.isLoading}
                 rows={artists.data?.map((r) => ({ id: r.id, name: r.name, image_url: r.image_url, streams: r.streams, minutes: r.minutes }))} />
      </div>
      <ListeningClock data={clock.data} loading={clock.isLoading} />
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card">
          <h2 className="mb-3 font-semibold">{t("topGenres")}</h2>
          <div className="flex flex-wrap gap-2">
            {genres.data?.map((g) => <span key={g.name} className="chip">{g.name} · {Math.round(g.weighted_streams)}</span>)}
          </div>
        </section>
        <section className="card">
          <h2 className="mb-3 font-semibold">{t("recentMilestones")}</h2>
          <MilestoneList rows={milestones.data} />
        </section>
      </div>
    </Page>
  );
}
