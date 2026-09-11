"use client";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/ui/Page";
import { Toggle } from "@/components/ui/Toggle";
import { LocaleSwitcher } from "@/components/layout/LocaleSwitcher";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Me } from "@/lib/types";

export default function SettingsPage() {
  const t = useTranslations("settings");
  const qc = useQueryClient();
  const router = useRouter();
  const { data: me } = useMe();
  const patch = useMutation({
    mutationFn: (body: Partial<Me["preferences"]>) => api("/api/v1/me/preferences", { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  const del = useMutation({ mutationFn: () => api("/api/v1/me", { method: "DELETE" }), onSuccess: () => { qc.clear(); router.push("/"); } });
  const p = me?.preferences;
  return (
    <Page title={t("title")}>
      <section className="card space-y-3">
        <div className="flex items-center justify-between"><span className="text-sm">{t("language")}</span><LocaleSwitcher persist /></div>
        <label className="block text-sm">
          <span className="text-fg-muted">{t("timezone")}</span>
          <input className="input mt-1" defaultValue={p?.timezone ?? "UTC"} onBlur={(e) => patch.mutate({ timezone: e.target.value })} list="tz" />
          <datalist id="tz">{Intl.supportedValuesOf?.("timeZone").map((z) => <option key={z} value={z} />)}</datalist>
          <span className="text-xs text-fg-subtle">{t("timezoneHint")}</span>
        </label>
        <Toggle label={t("logger")} checked={!!p?.stream_logger_enabled} onChange={(v) => patch.mutate({ stream_logger_enabled: v })} />
      </section>
      <section className="card">
        <h2 className="mb-1 font-semibold">{t("privacy")}</h2>
        <Toggle label={t("shareFriends")} checked={!!p?.share_stats_with_friends} onChange={(v) => patch.mutate({ share_stats_with_friends: v })} />
        <Toggle label={t("shareGlobal")} checked={!!p?.share_stats_globally} onChange={(v) => patch.mutate({ share_stats_globally: v })} />
      </section>
      <section className="card border-danger/40">
        <h2 className="mb-2 font-semibold text-danger">{t("danger")}</h2>
        <button className="btn-danger" onClick={() => { if (confirm(t("deleteConfirm"))) del.mutate(); }}>{t("deleteAccount")}</button>
      </section>
    </Page>
  );
}
