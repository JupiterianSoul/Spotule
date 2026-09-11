import { clsx, type ClassValue } from "clsx";

export const cn = (...inputs: ClassValue[]) => clsx(inputs);

export const fmtMinutes = (locale: string, minutes: number) =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(minutes);

export const fmtCompact = (locale: string, n: number) =>
  new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(n);
