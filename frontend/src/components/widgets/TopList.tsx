"use client";
import { useLocale, useTranslations } from "next-intl";
import { Skeleton } from "@/components/ui/Skeleton";
import { fmtCompact } from "@/lib/utils";

export interface TopRow { id: string; name: string; subtitle?: string | null; image_url?: string | null; streams: number; minutes?: number }

export function TopList({ title, rows, loading, square = true }: { title: string; rows?: TopRow[]; loading?: boolean; square?: boolean }) {
  const locale = useLocale();
  const t = useTranslations();
  return (
    <section className="card">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {loading && <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-11" />)}</div>}
      {!loading && !rows?.length && <p className="text-sm text-fg-subtle">{t("stats.empty")}</p>}
      <ol className="space-y-1">
        {rows?.map((r, i) => (
          <li key={r.id} className="flex items-center gap-3 rounded-md px-1 py-1.5 hover:bg-surface/60">
            <span className="w-6 text-right text-sm tabular-nums text-fg-subtle">{i + 1}</span>
            {r.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={r.image_url} alt="" className={`h-10 w-10 shrink-0 object-cover ${square ? "rounded" : "rounded-full"}`} />
            ) : <div className={`h-10 w-10 shrink-0 bg-surface ${square ? "rounded" : "rounded-full"}`} />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{r.name}</p>
              {r.subtitle && <p className="truncate text-xs text-fg-muted">{r.subtitle}</p>}
            </div>
            <div className="text-right text-xs tabular-nums text-fg-muted">
              <div>{t("common.streams", { count: r.streams })}</div>
              {r.minutes !== undefined && <div className="text-fg-subtle">{fmtCompact(locale, r.minutes)} min</div>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
