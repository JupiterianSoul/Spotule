export type TimeframePreset = "4w" | "6m" | "1y" | "lifetime" | "custom";

export interface Me {
  user: { id: string; spotify_id: string; display_name: string | null; email: string | null;
          avatar_url: string | null; country: string | null; product: string | null; role: string };
  preferences: { locale: "en" | "fr"; timezone: string; skip_guard_enabled: boolean;
                 stream_logger_enabled: boolean; share_stats_with_friends: boolean;
                 share_stats_globally: boolean; settings: Record<string, unknown> };
  spotify_linked: boolean;
  scopes: string[];
}

export interface Overview { streams: number; minutes: number; unique_tracks: number; unique_artists: number; skips: number }
export interface TopTrack { id: string; name: string; image_url: string | null; album: string | null; streams: number; minutes: number }
export interface TopArtist { id: string; name: string; image_url: string | null; streams: number; minutes: number }
export interface TopAlbum { id: string; name: string; image_url: string | null; artist: string | null; streams: number; minutes: number }
export interface TopGenre { name: string; weighted_streams: number; streams: number }
export interface Clock { timezone: string; grid: number[][]; minutes: number[][]; by_hour: number[]; by_weekday: number[]; peak_hour: number; peak_weekday: number }
export interface Milestone { id: string; kind: string; threshold: number; entity_id: string; entity_name: string | null; achieved_at: string; value: number; new: boolean }
export interface LeaderboardRow { rank: number; user_id: string; display_name: string | null; avatar_url: string | null; value: number; is_me: boolean }

export interface BannedGenre { id: string; pattern: string; match_mode: "contains" | "exact" | "regex"; apply_skip_guard: boolean; apply_library_purge: boolean; is_active: boolean; note: string | null; created_at: string }
export interface SkipEvent { id: number; track_name: string | null; matched_genre: string | null; matched_rule: string | null; device_type: string | null; detected_at: string; latency_ms: number | null; success: boolean }
export interface PurgeStatus { run_id: string; status: string; dry_run: boolean; scanned: number; matched: number; removed: number; report: { track_id: string; name: string; artist: string; genre: string; rule: string }[]; error: string | null }

export interface ToolSpec { key: string; pillar: string; destructive: boolean; needs_premium: boolean; async_run: boolean; params_schema: Record<string, unknown>; title: string; description: string }
export interface JobRef { run_id: string; status: string; tool_key: string | null; progress: number; result: Record<string, unknown>; error: string | null }
export interface ImportJob { id: string; filename: string; status: string; files_total: number; files_done: number; rows_total: number; rows_inserted: number; rows_skipped_duplicate: number; rows_skipped_invalid: number; earliest: string | null; latest: string | null; error: string | null; created_at: string }
export interface Automation { id: string; kind: string; cron: string; enabled: boolean; config: Record<string, unknown>; last_run_at: string | null; next_run_at: string | null }
export interface PlaylistSummary { id: string; name: string; owner: string; is_owner: boolean; public: boolean | null; tracks: number; image: string | null }

export interface Person { user_id: string; display_name: string | null; avatar_url: string | null; spotify_id: string; shares_stats: boolean }
export interface FriendLink { link_id: string; person: Person; status: "pending" | "accepted" | "blocked"; direction: "outgoing" | "incoming" | "mutual" }
