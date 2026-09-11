"use client";
import { useRef, useState } from "react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UploadCloud } from "lucide-react";
import { Page } from "@/components/ui/Page";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { ImportJob } from "@/lib/types";

export default function ImportsPage() {
  const t = useTranslations("imports");
  const locale = useLocale();
  const f = useFormatter();
  const qc = useQueryClient();
  const jobs = useApi<ImportJob[]>(["imports"], "/api/v1/imports");
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api("/api/v1/imports", { method: "POST", formData: fd, locale }); },
    onSuccess: () => { setError(null); qc.invalidateQueries({ queryKey: ["imports"] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  return (
    <Page title={t("title")} subtitle={t("subtitle")}>
      <label className="card flex cursor-pointer flex-col items-center justify-center gap-2 border-dashed py-10 text-fg-muted hover:border-fg-subtle"
             onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const fl = e.dataTransfer.files[0]; if (fl) upload.mutate(fl); }}>
        <UploadCloud className="h-8 w-8 text-accent" />
        <span className="text-sm">{t("drop")}</span>
        <input ref={fileRef} type="file" accept=".zip" className="hidden" onChange={(e) => { const fl = e.target.files?.[0]; if (fl) upload.mutate(fl); }} />
      </label>
      {error && <p className="rounded-md bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
      <section className="card">
        <h2 className="mb-2 font-semibold">{t("jobs")}</h2>
        <ul className="divide-y divide-border text-sm">
          {jobs.data?.map((j) => (
            <li key={j.id} className="space-y-1 py-3">
              <div className="flex items-center gap-2">
                <span className="flex-1 truncate">{j.filename}</span>
                <span className="chip">{t(`status.${j.status as "queued" | "running" | "succeeded" | "failed"}`)}</span>
              </div>
              <p className="text-xs text-fg-muted">{t("rows", { inserted: j.rows_inserted, dupes: j.rows_skipped_duplicate })}</p>
              {j.earliest && j.latest && <p className="text-xs text-fg-subtle">{t("range", { from: f.dateTime(new Date(j.earliest), "long"), to: f.dateTime(new Date(j.latest), "long") })}</p>}
              {j.status === "running" && <div className="h-1.5 rounded bg-surface"><div className="h-1.5 rounded bg-accent" style={{ width: `${j.files_total ? (100 * j.files_done) / j.files_total : 5}%` }} /></div>}
              {j.error && <p className="text-xs text-danger">{j.error}</p>}
            </li>
          ))}
        </ul>
      </section>
    </Page>
  );
}
