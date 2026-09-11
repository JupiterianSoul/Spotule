import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// Server-side only: where the FastAPI container actually lives.
// Never exposed to the browser — the browser only ever talks to this Next app.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Same-origin API. Keeps the session cookie first-party (SameSite=Lax works everywhere,
  // including Safari and Chrome's third-party cookie blocking) and removes CORS entirely.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` },
      { source: "/healthz", destination: `${API_INTERNAL_URL}/healthz` },
    ];
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "i.scdn.co" },
      { protocol: "https", hostname: "mosaic.scdn.co" },
      { protocol: "https", hostname: "image-cdn-*.spotifycdn.com" },
    ],
  },
};

export default withNextIntl(nextConfig);
