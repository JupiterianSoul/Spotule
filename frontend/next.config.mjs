import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // The API is proxied by src/app/api/[...path]/route.ts rather than a rewrite, because
  // rewrite destinations are frozen at build time and API_INTERNAL_URL is a runtime value.
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "i.scdn.co" },
      { protocol: "https", hostname: "mosaic.scdn.co" },
      { protocol: "https", hostname: "image-cdn-*.spotifycdn.com" },
    ],
  },
};

export default withNextIntl(nextConfig);
