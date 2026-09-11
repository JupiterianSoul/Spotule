"""Audio Porter — paste Apple Music / YouTube Music text or URLs → Spotify playlist.

Stage 1 (this scaffold): parse "Artist - Title" lines and search Spotify.
Stage 2: URL scrapers (Apple Music pages embed a JSON-LD track list; YouTube Music via
`ytmusicapi`), all producing the same `[{artist, title, isrc?}]` shape for the matcher.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.services.tools.base import Tool, ToolContext, registry

_LINE = re.compile(r"^\s*(?:\d+[.)]\s*)?(?P<artist>.+?)\s+[-–—]\s+(?P<title>.+?)\s*$")


def parse_lines(text: str) -> list[dict[str, str]]:
    out = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m:
            out.append({"artist": m["artist"], "title": m["title"]})
    return out


def _clean(s: str) -> str:
    return re.sub(r"\s*[\(\[].*?(feat|remaster|version|edit|live)[^\)\]]*[\)\]]", "", s, flags=re.I).strip()


@registry.register
class AudioPorter(Tool):
    key = "porter.text_to_playlist"
    pillar = "porter"

    class Params(BaseModel):
        text: str = Field(..., description="One track per line: 'Artist - Title'")
        name: str
        market: str | None = None

    async def run(self, ctx: ToolContext, params: Params) -> dict[str, Any]:
        wanted = parse_lines(params.text)
        found: list[str] = []
        misses: list[dict] = []
        for i, w in enumerate(wanted):
            q = f"track:{_clean(w['title'])} artist:{_clean(w['artist'])}"
            res = await ctx.client.search(q, "track", 3, params.market or ctx.user.country)
            items = res.get("tracks", {}).get("items", [])
            if not items:  # loosen
                res = await ctx.client.search(f"{w['artist']} {w['title']}", "track", 3, params.market)
                items = res.get("tracks", {}).get("items", [])
            if items:
                found.append(items[0]["uri"])
            else:
                misses.append(w)
            ctx.report_progress(int(90 * (i + 1) / max(len(wanted), 1)))
        new = await ctx.client.create_playlist(ctx.user.spotify_id, params.name, "Ported with Spotule")
        await ctx.client.add_items(new["id"], found)
        return {"playlist_id": new["id"], "matched": len(found), "unmatched": misses}
