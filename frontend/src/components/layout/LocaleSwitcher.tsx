"use client";
import { useLocale, useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type Locale } from "@/i18n/routing";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Toggles the URL locale segment and (when signed in) persists the preference server-side. */
export function LocaleSwitcher({ persist = false }: { persist?: boolean }) {
  const locale = useLocale();
  const t = useTranslations("locale");
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams();

  const change = (next: Locale) => {
    if (next === locale) return;
    if (persist) api("/api/v1/me/preferences", { method: "PATCH", body: { locale: next } }).catch(() => {});
    // @ts-expect-error -- params are known to match the current pathname
    router.replace({ pathname, params }, { locale: next });
  };

  return (
    <div role="group" aria-label={t("switch")} className="flex rounded-full bg-surface p-0.5">
      {routing.locales.map((l) => (
        <button key={l} onClick={() => change(l)} aria-pressed={l === locale}
          className={cn("rounded-full px-3 py-1 text-xs font-semibold uppercase transition-colors",
            l === locale ? "bg-fg text-bg" : "text-fg-muted hover:text-fg")}>
          {l}
        </button>
      ))}
    </div>
  );
}
