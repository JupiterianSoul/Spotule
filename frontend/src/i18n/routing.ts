import { defineRouting } from "next-intl/routing";

export const locales = ["en", "fr"] as const;
export type Locale = (typeof locales)[number];

export const routing = defineRouting({
  locales,
  defaultLocale: "en",
  localePrefix: "always", // /en/dashboard, /fr/dashboard — shareable, cache-friendly URLs
  localeDetection: true,  // first visit: Accept-Language → cookie NEXT_LOCALE afterwards
});
