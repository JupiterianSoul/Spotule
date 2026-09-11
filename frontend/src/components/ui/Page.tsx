import { TopBar } from "@/components/layout/TopBar";

export function Page({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <>
      <TopBar title={title} />
      <main className="pb-safe flex-1 space-y-6 px-4 py-5 md:px-8 md:py-6">
        {subtitle && <p className="-mt-2 text-sm text-fg-muted">{subtitle}</p>}
        {children}
      </main>
    </>
  );
}
