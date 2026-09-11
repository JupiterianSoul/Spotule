"use client";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Page } from "@/components/ui/Page";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { JobRef, ToolSpec } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ToolRunner } from "@/features/tools/ToolRunner";

const PILLARS = ["playlists", "bulk", "sonic", "backup", "porter", "library"] as const;

export default function ToolsPage() {
  const t = useTranslations("tools");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();
  const tools = useApi<ToolSpec[]>(["tools", locale], "/api/v1/tools", { lang: locale });
  const runs = useApi<JobRef[]>(["tool-runs"], "/api/v1/tools/runs");
  const [pillar, setPillar] = useState<string>("playlists");
  const [open, setOpen] = useState<ToolSpec | null>(null);
  const run = useMutation({
    mutationFn: ({ key, params }: { key: string; params: Record<string, unknown> }) => api<JobRef>(`/api/v1/tools/${key}/run`, { method: "POST", body: params, locale }),
    onSuccess: () => { setOpen(null); qc.invalidateQueries({ queryKey: ["tool-runs"] }); },
  });

  return (
    <Page title={t("title")} subtitle={t("subtitle")}>
      <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <div className="flex w-max gap-2">
          {PILLARS.map((p) => <button key={p} onClick={() => setPillar(p)} className={cn(pillar === p ? "chip-active" : "chip")}>{t(`pillars.${p}`)}</button>)}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {tools.data?.filter((s) => s.pillar === pillar).map((s) => (
          <button key={s.key} onClick={() => setOpen(s)} className="card text-left transition-colors hover:border-fg-subtle">
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-semibold">{s.title}</h2>
              {s.needs_premium && <span className="chip">{t("premium")}</span>}
            </div>
            <p className="mt-1 text-sm text-fg-muted">{s.description}</p>
            {s.destructive && <p className="mt-2 flex items-center gap-1 text-xs text-warning"><AlertTriangle className="h-3 w-3" /> {t("destructive")}</p>}
          </button>
        ))}
        {tools.data && !tools.data.some((s) => s.pillar === pillar) && <p className="text-sm text-fg-subtle">{tc("comingSoon")}</p>}
      </div>
      {open && <ToolRunner spec={open} pending={run.isPending} onClose={() => setOpen(null)} onRun={(params) => run.mutate({ key: open.key, params })} />}
      <section className="card">
        <h2 className="mb-2 font-semibold">{t("runs")}</h2>
        <ul className="divide-y divide-border text-sm">
          {runs.data?.map((r) => (
            <li key={r.run_id} className="flex items-center gap-3 py-2">
              <span className="flex-1 truncate font-mono text-xs">{r.tool_key}</span>
              <span className="chip">{r.status}</span>
              <span className="w-12 text-right text-xs tabular-nums text-fg-muted">{t("progress", { pct: r.progress })}</span>
            </li>
          ))}
        </ul>
      </section>
    </Page>
  );
}
