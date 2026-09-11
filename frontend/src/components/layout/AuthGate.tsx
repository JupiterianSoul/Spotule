"use client";
import { useLocale, useTranslations } from "next-intl";
import { loginUrl } from "@/lib/api";
import { useMe } from "@/lib/hooks";

/** Client-side guard: the session cookie is HttpOnly on the API origin, so the
 *  Next server can't read it — we probe /me and render a sign-in card on 401. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const locale = useLocale();
  const t = useTranslations();
  const { data, isLoading, isError } = useMe();
  if (isLoading) return <div className="p-8 text-fg-muted">{t("common.loading")}</div>;
  if (isError || !data) {
    return (
      <div className="flex min-h-[60dvh] items-center justify-center p-6">
        <div className="card max-w-sm text-center">
          <p className="mb-4 text-fg-muted">{t("app.tagline")}</p>
          <a href={loginUrl(locale, window.location.pathname.replace(`/${locale}`, "") || "/dashboard")} className="btn-primary">
            {t("auth.signIn")}
          </a>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
