import { NextResponse } from "next/server";

/** Health probe for the web service. Reports whether the API behind it is reachable too,
 *  which is what platform health checks and the scheduler's cold-start retry care about. */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const base = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const upstream = await fetch(`${base}/healthz`, { cache: "no-store" });
    return NextResponse.json({ ok: upstream.ok, web: true, api: upstream.ok });
  } catch {
    return NextResponse.json({ ok: false, web: true, api: false }, { status: 503 });
  }
}
