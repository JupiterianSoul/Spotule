import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

// Next 16 renamed middleware.ts → proxy.ts; next-intl's handler is unchanged.
export default createMiddleware(routing);

export const config = {
  // Skip API routes, Next internals and static files
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
