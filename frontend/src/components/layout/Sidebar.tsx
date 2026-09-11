"use client";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { NAV } from "./nav";

export function Sidebar() {
  const t = useTranslations("nav");
  const tApp = useTranslations("app");
  const pathname = usePathname();
  return (
    <aside className="hidden w-60 shrink-0 flex-col gap-1 border-r border-border bg-black/40 p-4 md:flex">
      <Link href="/dashboard" className="mb-4 px-2 text-xl font-extrabold tracking-tight">{tApp("name")}</Link>
      {NAV.map(({ href, key, Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link key={href} href={href}
            className={cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active ? "bg-surface text-fg" : "text-fg-muted hover:bg-surface/60 hover:text-fg")}>
            <Icon className="h-4 w-4" /> {t(key)}
          </Link>
        );
      })}
    </aside>
  );
}
