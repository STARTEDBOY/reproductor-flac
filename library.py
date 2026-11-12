"""Escaneo de la biblioteca musical y extracción de portadas.

Solo se leen etiquetas al escanear; las portadas se extraen cuando hacen
falta y se guardan en caché para no volver a decodificarlas.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.flac import FLAC, Picture

SUPPORTED = {
    ".flac", ".mp3", ".ogg", ".oga", ".opus", ".m4a", ".mp4",
    ".wav", ".aiff", ".aif", ".ape", ".wv",
}

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "reproductor-flac"


@dataclass(slots=True, frozen=True)
class Track:
    path: str
    title: str
    artist: str
    album: str
    albumartist: str
    duration: float
    tracknumber: int
    discnumber: int
    year: str
    genre: str
    sample_rate: int
    bit_depth: int
    has_cover: bool
    suffix: str

    @property
    def display_artist(self) -> str:
        return self.artist or self.albumartist or "Artista desconocido"

    @property
    def display_album(self) -> str:
        return self.album or "Álbum desconocido"

    @property
    def album_key(self) -> str:
        return f"{self.albumartist or self.artist}|{self.album}"

    @property
    def quality(self) -> str:
        bits = f"{self.bit_depth} BIT" if self.bit_depth else self.suffix.upper().lstrip(".")
        hz = f"{self.sample_rate / 1000:g} KHZ" if self.sample_rate else ""
        return " · ".join(part for part in (bits, hz) if part)


def format_time(seconds: float) -> str:
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return "0:00"
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _load(path: Path):
    if path.suffix.lower() == ".flac":
        return FLAC(path)
    return mutagen.File(path)


def _first(tags, *keys: str) -> str:
    if tags is None:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            value = value[0]
        text = str(value).strip()
        if text:
            return text
    return ""


def _number(text: str) -> int:
    text = text.split("/")[0].strip()
    try:
        return int(text)
    except ValueError:
        return 0


def _has_cover(audio) -> bool:
    if getattr(audio, "pictures", None):
        return True
    tags = audio.tags
    if tags is None:
        return False
    try:
        if "covr" in tags:
            return True
    except Exception:
        pass
    return any(str(key).startswith("APIC") for key in tags.keys())


def read_track(path: Path) -> Track | None:
    try:
        audio = _load(path)
    except Exception:
        return None
    if audio is None or getattr(audio, "info", None) is None:
        return None

    tags = audio.tags
    title = _first(tags, "title", "TIT2", "\xa9nam") or path.stem
    artist = _first(tags, "artist", "TPE1", "\xa9ART")
    album = _first(tags, "album", "TALB", "\xa9alb")
    albumartist = _first(
        tags, "albumartist", "album artist", "TPE2", "aART", "\xa9ART"
    )
    year = _first(tags, "date", "year", "TDRC", "DATE", "\xa9day")
    genre = _first(tags, "genre", "TCON", "\xa9gen")
    tracknumber = _number(_first(tags, "tracknumber", "track", "TRCK", "trkn"))
    discnumber = _number(_first(tags, "discnumber", "disc", "TPOS", "disk"))

    info = audio.info
    return Track(
        path=str(path),
        title=title,
        artist=artist,
        album=album,
        albumartist=albumartist,
        duration=float(getattr(info, "length", 0) or 0),
        tracknumber=tracknumber,
        discnumber=discnumber,
        year=year,
        genre=genre,
        sample_rate=int(getattr(info, "sample_rate", 0) or 0),
        bit_depth=int(getattr(info, "bits_per_sample", 0) or 0),
        has_cover=_has_cover(audio),
        suffix=path.suffix.lower(),
    )


def _sort_key(track: Track):
    return (
        (track.albumartist or track.artist).casefold(),
        track.album.casefold(),
        track.discnumber,
        track.tracknumber,
        track.title.casefold(),
        track.path.casefold(),
    )


def scan_library(root: str | Path) -> list[Track]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"No existe la carpeta: {root}")

    tracks: list[Track] = []
    for path in root.rglob("*"):
        try:
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                continue
        except OSError:
            continue
        try:
            track = read_track(path)
        except Exception:
            track = None
        if track is not None:
            tracks.append(track)

    tracks.sort(key=_sort_key)
    return tracks


def _raw_cover(audio) -> bytes | None:
    pictures = getattr(audio, "pictures", None)
    if pictures:
        return pictures[0].data

    tags = audio.tags
    if tags is None:
        return None

    try:
        if "covr" in tags:
            return bytes(tags["covr"][0])
    except Exception:
        pass

    for key in list(tags.keys()):
        if str(key).startswith("APIC"):
            try:
                return bytes(tags[key].data)
            except Exception:
                pass

    for key in ("metadata_block_picture", "METADATA_BLOCK_PICTURE"):
        try:
            value = tags.get(key)
        except Exception:
            value = None
        if not value:
            continue
        try:
            if isinstance(value, (list, tuple)):
                value = value[0]
            return Picture(base64.b64decode(value)).data
        except Exception:
            pass

    return None


def get_cover_bytes(track: Track) -> bytes | None:
    """Devuelve la portada incrustada, usando caché en disco por álbum."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(track.album_key.encode("utf-8", "replace")).hexdigest()[:20]
    cached = CACHE_DIR / f"{key}.img"
    missing = CACHE_DIR / f"{key}.none"

    if cached.exists():
        try:
            return cached.read_bytes()
        except OSError:
            pass
    if missing.exists():
        return None

    try:
        audio = _load(Path(track.path))
        data = _raw_cover(audio) if audio is not None else None
    except Exception:
        data = None

    if data:
        try:
            cached.write_bytes(data)
            if missing.exists():
                missing.unlink()
        except OSError:
            pass
        return data

    try:
        missing.write_text("", encoding="utf-8")
    except OSError:
        pass
    return None


def library_summary(tracks: list[Track]) -> str:
    albums = len({(t.albumartist or t.artist, t.album) for t in tracks})
    return f"{len(tracks)} PISTAS · {albums} ÁLBUMES"
