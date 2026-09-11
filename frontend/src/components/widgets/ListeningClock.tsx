"use client";
import { useTranslations } from "next-intl";
import type { Clock } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";

/** 7×24 heatmap; CSS grid so it stays crisp on phones (scrolls horizontally if needed). */
export function ListeningClock({ data, loading }: { data?: Clock; loading?: boolean }) {
  const t = useTranslations("stats.clock");
  const weekdays = t.raw("weekdays") as string[];
  const max = data ? Math.max(1, ...data.grid.flat()) : 1;
  return (
    <section className="card">
      <h2 className="mb-1 font-semibold">{t("title")}</h2>
      {data && <p className="mb-3 text-xs text-fg-muted">{t("peak", { day: weekdays[data.peak_weekday], hour: data.peak_hour })}</p>}
      {loading && <Skeleton className="h-48" />}
      {data && (
        <div className="overflow-x-auto">
          <div className="grid min-w-[560px] gap-0.5" style={{ gridTemplateColumns: "2.5rem repeat(24, minmax(0, 1fr))" }}>
            <div />
            {Array.from({ length: 24 }).map((_, h) => <div key={h} className="text-center text-[10px] text-fg-subtle">{h % 3 === 0 ? h : ""}</div>)}
            {data.grid.map((row, d) => (
              <>
                <div key={`l${d}`} className="pr-2 text-right text-[11px] text-fg-muted">{weekdays[d]}</div>
                {row.map((v, h) => (
                  <div key={`${d}-${h}`} title={`${weekdays[d]} ${h}h · ${v}`} className="aspect-square rounded-sm"
                       style={{ backgroundColor: `rgba(29,185,84,${v === 0 ? 0.06 : 0.15 + 0.85 * (v / max)})` }} />
                ))}
              </>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
