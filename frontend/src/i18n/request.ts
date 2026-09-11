import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
    timeZone: "UTC",
    // Shared number/date formats so every widget renders "12 345 min" in fr and "12,345 min" in en
    formats: {
      number: { compact: { notation: "compact", maximumFractionDigits: 1 } },
      dateTime: { short: { day: "numeric", month: "short" }, long: { dateStyle: "long" } },
    },
  };
});
