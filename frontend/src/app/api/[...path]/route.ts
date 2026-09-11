import { type NextRequest, NextResponse } from "next/server";

/**
 * Runtime reverse proxy: browser -> this Next server -> FastAPI.
 *
 * Why a route handler instead of next.config `rewrites()`: rewrite destinations are resolved
 * during `next build` and frozen into routes-manifest.json, so `API_INTERNAL_URL` set at
 * runtime (Render, Docker Compose, anywhere the API lives on another host) would be ignored
 * and every request would go to the build-time default. This reads the variable per request.
 *
 * Keeping the API on the page's own origin is what makes the session cookie first-party.
 * Cross-site cookies are blocked by Safari and restricted by Chrome, so a split origin would
 * break sign-in for some people with no visible error.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const apiBase = () => (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

// Connection-level headers must not be forwarded in either direction.
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

// fetch() already decompresses, so echoing these would describe the body incorrectly.
const STRIP_FROM_RESPONSE = new Set(["content-encoding", "content-length", ...HOP_BY_HOP]);

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${apiBase()}/api/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`;

  const headers = new Headers(req.headers);
  for (const name of HOP_BY_HOP) headers.delete(name);
  headers.delete("host");
  headers.delete("content-length"); // recomputed by fetch for streamed bodies
  // Node's fetch rejects Expect outright ("expect header not supported"). curl adds
  // `Expect: 100-continue` to file uploads, so forwarding it would break every upload
  // from a CLI client. The handshake is between us and the upstream, not the client.
  headers.delete("expect");

  const hasBody = req.method !== "GET" && req.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // Required by Node when sending a streamed request body (keeps large uploads, such as
      // the Spotify data-export ZIP, from being buffered in memory).
      ...(hasBody ? { duplex: "half" } : {}),
      // Pass 3xx straight back: the OAuth login endpoint redirects the browser to Spotify,
      // and following it here would break the flow.
      redirect: "manual",
      cache: "no-store",
    } as RequestInit);
  } catch (error) {
    // Free hosts suspend idle services; a cold start can refuse the first connection.
    console.error("[api-proxy] upstream request failed", { target, method: req.method, error });
    return NextResponse.json(
      { detail: "The API is unreachable. If it is waking from sleep, retry in a moment." },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!STRIP_FROM_RESPONSE.has(key.toLowerCase()) && key.toLowerCase() !== "set-cookie") {
      responseHeaders.append(key, value);
    }
  });
  // Set-Cookie can appear more than once and must not be folded into one header.
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
export const OPTIONS = proxy;
