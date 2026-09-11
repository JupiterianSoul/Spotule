"use client";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "next-intl";
import { api } from "./api";
import type { Me, TimeframePreset } from "./types";

export function useMe() {
  const locale = useLocale();
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/me", { locale }), retry: false, staleTime: 60_000 });
}

export function useApi<T>(key: unknown[], path: string, query?: Record<string, string | number | undefined>, enabled = true) {
  const locale = useLocale();
  return useQuery({ queryKey: [...key, query], queryFn: () => api<T>(path, { query, locale }), enabled, staleTime: 30_000 });
}

export type Timeframe = { preset: TimeframePreset; start?: string; end?: string };
export const tfQuery = (tf: Timeframe) => ({ preset: tf.preset, start: tf.start, end: tf.end });
