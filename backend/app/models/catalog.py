"""Shared (non-tenant) Spotify catalogue cache: artists, albums, tracks, genres, audio features.

Rows are keyed by Spotify IDs and shared across all users — one fetch benefits everyone and
dramatically reduces API calls. Genres live on artists in Spotify's model; we normalise them
into a `genres` table so 'Top Genres' and the Ban-Hammer are simple joins.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AudioFeatureSource


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # lower-cased


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # Spotify artist id
    name: Mapped[str] = mapped_column(String(512), index=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    popularity: Mapped[int | None] = mapped_column(SmallInteger)
    followers: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    genres: Mapped[list[Genre]] = relationship(secondary="artist_genres", lazy="selectin")


class ArtistGenre(Base):
    __tablename__ = "artist_genres"

    artist_id: Mapped[str] = mapped_column(ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    album_type: Mapped[str | None] = mapped_column(String(16))  # album / single / compilation
    release_date: Mapped[str | None] = mapped_column(String(10))  # Spotify precision varies
    image_url: Mapped[str | None] = mapped_column(Text)
    primary_artist_id: Mapped[str | None] = mapped_column(
        ForeignKey("artists.id", ondelete="SET NULL"), index=True
    )
    total_tracks: Mapped[int | None] = mapped_column(SmallInteger)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    album_id: Mapped[str | None] = mapped_column(ForeignKey("albums.id", ondelete="SET NULL"), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    explicit: Mapped[bool | None] = mapped_column(Boolean)
    popularity: Mapped[int | None] = mapped_column(SmallInteger)
    isrc: Mapped[str | None] = mapped_column(String(16), index=True)  # cross-service matching
    preview_url: Mapped[str | None] = mapped_column(Text)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    artists: Mapped[list[Artist]] = relationship(
        secondary="track_artists", order_by="TrackArtist.position", lazy="selectin"
    )
    album: Mapped[Album | None] = relationship(lazy="selectin")
    audio_features: Mapped[AudioFeatures | None] = relationship(back_populates="track", uselist=False)


class TrackArtist(Base):
    __tablename__ = "track_artists"

    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    artist_id: Mapped[str] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class AudioFeatures(Base):
    """Sonic descriptors for Smart Sonic Filters. `source` matters: Spotify's /audio-features
    endpoint is restricted for apps created after 2024-11-27, so alternate providers are
    first-class here."""

    __tablename__ = "audio_features"

    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[AudioFeatureSource] = mapped_column(Enum(AudioFeatureSource, name="audio_feature_source"))
    tempo: Mapped[float | None] = mapped_column(Float)  # BPM
    energy: Mapped[float | None] = mapped_column(Float)
    valence: Mapped[float | None] = mapped_column(Float)  # "happiness"
    danceability: Mapped[float | None] = mapped_column(Float)
    acousticness: Mapped[float | None] = mapped_column(Float)
    instrumentalness: Mapped[float | None] = mapped_column(Float)
    liveness: Mapped[float | None] = mapped_column(Float)
    speechiness: Mapped[float | None] = mapped_column(Float)
    loudness: Mapped[float | None] = mapped_column(Float)
    key: Mapped[int | None] = mapped_column(SmallInteger)
    mode: Mapped[int | None] = mapped_column(SmallInteger)
    time_signature: Mapped[int | None] = mapped_column(SmallInteger)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    track: Mapped[Track] = relationship(back_populates="audio_features")
