import { getTranslations, setRequestLocale } from "next-intl/server";
import { hasLocale } from "next-intl";
import { notFound } from "next/navigation";
import { routing } from "@/i18n/routing";
import { loginUrl } from "@/lib/api";
import { LocaleSwitcher } from "@/components/layout/LocaleSwitcher";
import { Activity, Ban, Sparkles, Users } from "lucide-react";

export default async function Landing({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations("landing");
  const tApp = await getTranslations("app");
  const pillars = [
    { key: "tracking", Icon: Activity }, { key: "banhammer", Icon: Ban },
    { key: "tools", Icon: Sparkles }, { key: "friends", Icon: Users },
  ] as const;
  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col px-5 py-6">
      <header className="flex items-center justify-between">
        <span className="text-lg font-extrabold tracking-tight">{tApp("name")}</span>
        <LocaleSwitcher />
      </header>
      <section className="flex flex-1 flex-col items-start justify-center gap-6 py-16">
        <h1 className="max-w-3xl text-4xl font-black leading-tight md:text-6xl">{t("title")}</h1>
        <p className="max-w-2xl text-lg text-fg-muted">{t("subtitle")}</p>
        <a href={loginUrl(locale)} className="btn-primary px-6 py-3 text-base">{t("cta")}</a>
      </section>
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {pillars.map(({ key, Icon }) => (
          <div key={key} className="card">
            <Icon className="mb-3 h-6 w-6 text-accent" />
            <h2 className="font-semibold">{t(`pillars.${key}.title`)}</h2>
            <p className="mt-1 text-sm text-fg-muted">{t(`pillars.${key}.body`)}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
