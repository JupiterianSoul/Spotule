"""Blacklist evaluation — pure functions so the skip guard, purger and UI preview share logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import BannedArtist, BannedGenre, BlacklistExemption
from app.models.enums import ExemptionKind, MatchMode


@dataclass(frozen=True)
class Rule:
    pattern: str
    mode: MatchMode
    skip_guard: bool = True
    purge: bool = True

    def matches(self, genre: str) -> bool:
        g = genre.lower()
        p = self.pattern.lower()
        if self.mode == MatchMode.exact:
            return g == p
        if self.mode == MatchMode.contains:
            return p in g
        return re.search(self.pattern, g, flags=re.IGNORECASE) is not None


@dataclass
class Verdict:
    banned: bool
    rule: str | None = None
    genre: str | None = None
    artist_id: str | None = None
    reason: str = ""


@dataclass
class Blacklist:
    rules: list[Rule] = field(default_factory=list)
    banned_artist_ids: set[str] = field(default_factory=set)
    exempt_artist_ids: set[str] = field(default_factory=set)
    exempt_track_ids: set[str] = field(default_factory=set)
    exempt_album_ids: set[str] = field(default_factory=set)

    @classmethod
    def from_rows(
        cls, genres: list[BannedGenre], artists: list[BannedArtist], exemptions: list[BlacklistExemption]
    ) -> Blacklist:
        bl = cls(
            rules=[
                Rule(g.pattern, g.match_mode, g.apply_skip_guard, g.apply_library_purge)
                for g in genres
                if g.is_active
            ],
            banned_artist_ids={a.artist_id for a in artists if a.is_active},
        )
        for e in exemptions:
            {
                ExemptionKind.artist: bl.exempt_artist_ids,
                ExemptionKind.track: bl.exempt_track_ids,
                ExemptionKind.album: bl.exempt_album_ids,
            }[e.kind].add(e.spotify_id)
        return bl

    def evaluate(
        self,
        track_id: str | None,
        album_id: str | None,
        artists: dict[str, list[str]],
        *,
        context: str = "skip_guard",
    ) -> Verdict:
        """`artists` maps artist_id → genres. Exemptions win over bans."""
        if track_id in self.exempt_track_ids or album_id in self.exempt_album_ids:
            return Verdict(False, reason="exempt")
        for artist_id, genres in artists.items():
            if artist_id in self.exempt_artist_ids:
                continue
            if artist_id in self.banned_artist_ids:
                return Verdict(True, rule=f"artist:{artist_id}", artist_id=artist_id, reason="banned_artist")
            for genre in genres:
                for rule in self.rules:
                    if (context == "skip_guard" and not rule.skip_guard) or (
                        context == "purge" and not rule.purge
                    ):
                        continue
                    if rule.matches(genre):
                        return Verdict(
                            True, rule=rule.pattern, genre=genre, artist_id=artist_id, reason="genre"
                        )
        return Verdict(False)
