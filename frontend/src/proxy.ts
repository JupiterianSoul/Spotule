import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

// Next 16 renamed middleware.ts → proxy.ts; next-intl's handler is unchanged.
export default createMiddleware(routing);

export const config = {
  // Skip proxied API routes, the health probe, Next internals and static files —
  // these must never be rewritten to a /[locale]/ path.
  matcher: ["/((?!api|healthz|_next|_vercel|.*\\..*).*)"],
};
