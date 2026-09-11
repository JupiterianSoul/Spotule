"use client";
import { useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { useRouter } from "@/i18n/navigation";
import { LocaleSwitcher } from "./LocaleSwitcher";

export function TopBar({ title }: { title: string }) {
  const t = useTranslations("auth");
  const { data: me } = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const signOut = async () => {
    await api("/api/v1/auth/logout", { method: "POST" });
    qc.clear();
    router.push("/");
  };
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-border bg-bg/85 px-4 py-3 backdrop-blur md:px-8">
      <h1 className="truncate text-lg font-bold md:text-2xl">{title}</h1>
      <div className="flex items-center gap-3">
        <LocaleSwitcher persist />
        {me && (
          <div className="flex items-center gap-2">
            {me.user.avatar_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={me.user.avatar_url} alt="" className="h-8 w-8 rounded-full" />
            )}
            <span className="hidden text-sm text-fg-muted sm:inline">{me.user.display_name}</span>
            <button onClick={signOut} className="btn-ghost p-2" aria-label={t("signOut")}><LogOut className="h-4 w-4" /></button>
          </div>
        )}
      </div>
    </header>
  );
}
