"use client";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { NAV } from "./nav";

/** Bottom tab bar for Android/iOS browsers — 5 primary destinations, rest via Settings. */
export function MobileNav() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const items = NAV.filter((n) => ["dashboard", "stats", "banHammer", "tools", "settings"].includes(n.key));
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-black/90 backdrop-blur md:hidden"
         style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      {items.map(({ href, key, Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link key={href} href={href} aria-current={active ? "page" : undefined}
            className={cn("flex flex-1 flex-col items-center gap-1 py-2 text-[11px] font-medium",
              active ? "text-fg" : "text-fg-subtle")}>
            <Icon className={cn("h-5 w-5", active && "text-accent")} />
            {t(key)}
          </Link>
        );
      })}
    </nav>
  );
}
