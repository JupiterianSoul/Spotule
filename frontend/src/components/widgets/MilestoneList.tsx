"use client";
import { useFormatter, useTranslations } from "next-intl";
import { Trophy } from "lucide-react";
import type { Milestone } from "@/lib/types";

const KINDS = ["total_minutes", "total_streams", "artist_streams", "track_streams", "unique_artists", "unique_tracks"] as const;
type Kind = (typeof KINDS)[number];

export function MilestoneList({ rows }: { rows?: Milestone[] }) {
  const t = useTranslations("stats.milestones");
  const f = useFormatter();
  if (!rows?.length) return <p className="text-sm text-fg-subtle">{t("empty")}</p>;
  return (
    <ul className="space-y-2">
      {rows.map((m) => (
        <li key={m.id} className="flex items-center gap-3 rounded-md bg-surface/50 px-3 py-2">
          <Trophy className="h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm">
              {KINDS.includes(m.kind as Kind) ? t(m.kind as Kind, { value: m.threshold, entity: m.entity_name ?? "" }) : m.kind}
            </p>
            <p className="text-xs text-fg-subtle">{f.dateTime(new Date(m.achieved_at), "short")}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
