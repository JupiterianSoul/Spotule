import { Skeleton } from "@/components/ui/Skeleton";

export function StatTile({ label, value, hint, loading }: { label: string; value: string | number; hint?: string; loading?: boolean }) {
  return (
    <div className="card">
      <p className="text-xs font-medium uppercase tracking-wide text-fg-muted">{label}</p>
      {loading ? <Skeleton className="mt-2 h-8 w-24" /> : <p className="mt-1 text-2xl font-bold tabular-nums md:text-3xl">{value}</p>}
      {hint && <p className="mt-1 text-xs text-fg-subtle">{hint}</p>}
    </div>
  );
}
