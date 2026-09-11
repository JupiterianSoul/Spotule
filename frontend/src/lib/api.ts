/**
 * Typed fetch wrapper for the FastAPI backend.
 * - Sends the HttpOnly session cookie (credentials: "include").
 * - Forwards the active locale as Accept-Language so API error messages are localised.
 * - Throws ApiError with the backend's localised `detail`.
 */
/**
 * Empty by default: requests go to the same origin as the page and Next's rewrite
 * (see next.config.mjs) forwards them to FastAPI. Set NEXT_PUBLIC_API_BASE_URL only if
 * you deliberately want the browser to hit the API on another origin — you must then
 * also set COOKIE_SECURE=true and SameSite=None on the backend, and accept that some
 * browsers block the cookie outright.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function qs(params?: Query): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function api<T>(
  path: string,
  opts: { method?: string; body?: unknown; query?: Query; locale?: string; formData?: FormData } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.locale) headers["Accept-Language"] = opts.locale;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}${qs(opts.query)}`, {
    method: opts.method ?? "GET",
    credentials: "include",
    headers,
    body: opts.formData ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: string }).detail ?? res.statusText);
  return data as T;
}

export const loginUrl = (locale: string, next = "/dashboard") =>
  `${API_BASE}/api/v1/auth/login?lang=${locale}&next=${encodeURIComponent(next)}`;
