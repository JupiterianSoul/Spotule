"use client";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, UserMinus, UserPlus, X } from "lucide-react";
import { Page } from "@/components/ui/Page";
import { api, ApiError } from "@/lib/api";
import { useApi, useMe } from "@/lib/hooks";
import type { FriendLink, Person } from "@/lib/types";

function Avatar({ p }: { p: Person }) {
  return p.avatar_url ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={p.avatar_url} alt="" className="h-9 w-9 rounded-full object-cover" />
  ) : (
    <div className="h-9 w-9 rounded-full bg-surface" />
  );
}

export default function FriendsPage() {
  const t = useTranslations("friends");
  const tc = useTranslations("common");
  const locale = useLocale();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const links = useApi<FriendLink[]>(["friends"], "/api/v1/friends");
  const results = useQuery({
    queryKey: ["friend-search", q],
    queryFn: () => api<Person[]>("/api/v1/friends/search", { query: { q }, locale }),
    enabled: q.trim().length >= 2,
  });
  const invalidate = () => { qc.invalidateQueries({ queryKey: ["friends"] }); qc.invalidateQueries({ queryKey: ["leaderboard"] }); };
  const onError = (e: unknown) => setError(e instanceof ApiError ? e.message : tc("error"));

  const send = useMutation({ mutationFn: (user_id: string) => api("/api/v1/friends/requests", { method: "POST", body: { user_id }, locale }), onSuccess: () => { setError(null); invalidate(); }, onError });
  const accept = useMutation({ mutationFn: (link_id: string) => api(`/api/v1/friends/requests/${link_id}/accept`, { method: "POST", locale }), onSuccess: invalidate, onError });
  const remove = useMutation({ mutationFn: (user_id: string) => api(`/api/v1/friends/${user_id}`, { method: "DELETE", locale }), onSuccess: invalidate, onError });

  const linked = new Set(links.data?.map((l) => l.person.user_id));
  const incoming = links.data?.filter((l) => l.direction === "incoming") ?? [];
  const outgoing = links.data?.filter((l) => l.direction === "outgoing") ?? [];
  const mutual = links.data?.filter((l) => l.direction === "mutual") ?? [];

  const Row = ({ link, actions }: { link: FriendLink; actions: React.ReactNode }) => (
    <li className="flex items-center gap-3 py-2">
      <Avatar p={link.person} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{link.person.display_name ?? link.person.spotify_id}</p>
        {!link.person.shares_stats && <p className="text-xs text-fg-subtle">{t("notSharing")}</p>}
      </div>
      {actions}
    </li>
  );

  return (
    <Page title={t("title")} subtitle={t("subtitle")}>
      {error && <p className="rounded-md bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
      <section className="card">
        <label className="block text-sm">
          <span className="font-semibold">{t("search")}</span>
          <input className="input mt-2" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchHint")} />
        </label>
        {q.trim().length >= 2 && (
          <ul className="mt-3 divide-y divide-border">
            {results.data?.length === 0 && <li className="py-2 text-sm text-fg-subtle">{t("noResults")}</li>}
            {results.data?.map((p) => (
              <li key={p.user_id} className="flex items-center gap-3 py-2">
                <Avatar p={p} />
                <span className="flex-1 truncate text-sm">{p.display_name ?? p.spotify_id}</span>
                <button className="btn-primary py-1" disabled={linked.has(p.user_id) || send.isPending} onClick={() => send.mutate(p.user_id)}>
                  <UserPlus className="h-4 w-4" /> {t("add")}
                </button>
              </li>
            ))}
          </ul>
        )}
        {me && <p className="mt-3 text-xs text-fg-subtle">{t("shareLink", { id: me.user.spotify_id })}</p>}
      </section>

      {incoming.length > 0 && (
        <section className="card">
          <h2 className="mb-1 font-semibold">{t("incoming")}</h2>
          <ul className="divide-y divide-border">
            {incoming.map((l) => (
              <Row key={l.link_id} link={l} actions={<>
                <button className="btn-primary py-1" onClick={() => accept.mutate(l.link_id)}><Check className="h-4 w-4" /> {t("accept")}</button>
                <button className="btn-ghost py-1" onClick={() => remove.mutate(l.person.user_id)}><X className="h-4 w-4" /> {t("decline")}</button>
              </>} />
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h2 className="mb-1 font-semibold">{t("list")}</h2>
        {mutual.length === 0 && <p className="text-sm text-fg-subtle">{t("empty")}</p>}
        <ul className="divide-y divide-border">
          {mutual.map((l) => (
            <Row key={l.link_id} link={l} actions={
              <button className="btn-ghost py-1" onClick={() => remove.mutate(l.person.user_id)} aria-label={t("remove")}><UserMinus className="h-4 w-4" /></button>
            } />
          ))}
        </ul>
      </section>

      {outgoing.length > 0 && (
        <section className="card">
          <h2 className="mb-1 font-semibold">{t("outgoing")}</h2>
          <ul className="divide-y divide-border">
            {outgoing.map((l) => (
              <Row key={l.link_id} link={l} actions={
                <button className="btn-ghost py-1" onClick={() => remove.mutate(l.person.user_id)}>{t("cancel")}</button>
              } />
            ))}
          </ul>
        </section>
      )}
    </Page>
  );
}
