"use client";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Page } from "@/components/ui/Page";
import { TopList } from "@/components/widgets/TopList";
import { ListeningClock } from "@/components/widgets/ListeningClock";
import { MilestoneList } from "@/components/widgets/MilestoneList";
import { TimeframePicker } from "@/components/widgets/TimeframePicker";
import { useApi, tfQuery, type Timeframe } from "@/lib/hooks";
import type { Clock, LeaderboardRow, Milestone, TopAlbum, TopArtist, TopGenre, TopTrack } from "@/lib/types";
import { cn, fmtMinutes } from "@/lib/utils";

const TABS = ["tracks", "artists", "albums", "genres", "clock", "milestones", "leaderboard"] as const;
type Tab = (typeof TABS)[number];

export default function StatsPage() {
  const t = useTranslations("stats");
  const locale = useLocale();
  const [tab, setTab] = useState<Tab>("tracks");
  const [tf, setTf] = useState<Timeframe>({ preset: "4w" });
  const [scope, setScope] = useState<"friends" | "global">("friends");
  const q = tfQuery(tf);
  const isTop = ["tracks", "artists", "albums"].includes(tab);
  const top = useApi<(TopTrack | TopArtist | TopAlbum)[]>(["top", tab], `/api/v1/stats/top/${tab}`, { ...q, limit: 100 }, isTop);
  const genres = useApi<TopGenre[]>(["top", "genres"], "/api/v1/stats/top/genres", { ...q, limit: 50 }, tab === "genres");
  const clock = useApi<Clock>(["clock"], "/api/v1/stats/clock", q, tab === "clock");
  const milestones = useApi<Milestone[]>(["milestones"], "/api/v1/stats/milestones", { limit: 100 }, tab === "milestones");
  const board = useApi<LeaderboardRow[]>(["leaderboard", scope], "/api/v1/stats/leaderboard", { ...q, scope }, tab === "leaderboard");

  return (
    <Page title={t("title")}>
      <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <div className="flex w-max gap-2">
          {TABS.map((k) => <button key={k} onClick={() => setTab(k)} className={cn(tab === k ? "chip-active" : "chip")}>{t(`tabs.${k}`)}</button>)}
        </div>
      </div>
      {tab !== "milestones" && <TimeframePicker value={tf} onChange={setTf} />}
      {isTop && (
        <TopList title={t(`tabs.${tab}`)} loading={top.isLoading} square={tab !== "artists"}
          rows={top.data?.map((r) => ({ id: r.id, name: r.name, image_url: r.image_url, streams: r.streams, minutes: r.minutes,
            subtitle: "album" in r ? r.album : "artist" in r ? r.artist : undefined }))} />
      )}
      {tab === "genres" && (
        <section className="card space-y-2">
          {genres.data?.map((g, i) => {
            const max = genres.data?.[0]?.weighted_streams ?? 1;
            return (
              <div key={g.name} className="flex items-center gap-3 text-sm">
                <span className="w-6 text-right text-fg-subtle">{i + 1}</span>
                <span className="w-40 truncate">{g.name}</span>
                <div className="h-2 flex-1 rounded bg-surface"><div className="h-2 rounded bg-accent" style={{ width: `${(100 * g.weighted_streams) / max}%` }} /></div>
                <span className="w-12 text-right text-xs tabular-nums text-fg-muted">{Math.round(g.weighted_streams)}</span>
              </div>
            );
          })}
        </section>
      )}
      {tab === "clock" && <ListeningClock data={clock.data} loading={clock.isLoading} />}
      {tab === "milestones" && <section className="card"><MilestoneList rows={milestones.data} /></section>}
      {tab === "leaderboard" && (
        <section className="card">
          <div className="mb-3 flex gap-2">
            {(["friends", "global"] as const).map((s) => <button key={s} onClick={() => setScope(s)} className={cn(scope === s ? "chip-active" : "chip")}>{t(`leaderboard.${s}`)}</button>)}
          </div>
          {!board.data?.length && <p className="text-sm text-fg-subtle">{t("leaderboard.empty")}</p>}
          <ol className="space-y-1">
            {board.data?.map((r) => (
              <li key={r.user_id} className={cn("flex items-center gap-3 rounded-md px-2 py-1.5", r.is_me && "bg-accent/10")}>
                <span className="w-8 text-sm text-fg-subtle">{t("rank", { rank: r.rank })}</span>
                {r.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.avatar_url} alt="" className="h-8 w-8 rounded-full" />
                ) : <div className="h-8 w-8 rounded-full bg-surface" />}
                <span className="flex-1 truncate text-sm">{r.is_me ? t("leaderboard.you") : r.display_name}</span>
                <span className="text-sm tabular-nums">{fmtMinutes(locale, r.value)}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </Page>
  );
}
