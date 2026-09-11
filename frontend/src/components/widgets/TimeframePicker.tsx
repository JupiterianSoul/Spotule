"use client";
import { useTranslations } from "next-intl";
import type { Timeframe } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const PRESETS = ["4w", "6m", "1y", "lifetime", "custom"] as const;

export function TimeframePicker({ value, onChange }: { value: Timeframe; onChange: (tf: Timeframe) => void }) {
  const t = useTranslations("timeframe");
  return (
    <div className="flex flex-wrap items-center gap-2">
      {PRESETS.map((p) => (
        <button key={p} onClick={() => onChange({ ...value, preset: p })} className={cn(value.preset === p ? "chip-active" : "chip")}>{t(p)}</button>
      ))}
      {value.preset === "custom" && (
        <div className="flex items-center gap-2 text-xs">
          <label className="text-fg-muted">{t("from")}</label>
          <input type="date" className="input w-auto py-1" value={value.start ?? ""} onChange={(e) => onChange({ ...value, start: e.target.value })} />
          <label className="text-fg-muted">{t("to")}</label>
          <input type="date" className="input w-auto py-1" value={value.end ?? ""} onChange={(e) => onChange({ ...value, end: e.target.value })} />
        </div>
      )}
    </div>
  );
}
