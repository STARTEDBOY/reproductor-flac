"""Escaneo de la biblioteca musical y extracción de portadas.

Solo se leen etiquetas al escanear; las portadas se extraen cuando hacen
falta y se guardan en caché para no volver a decodificarlas.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path

import mutagen
from mutagen.flac import FLAC, Picture

from i18n import tr

SUPPORTED = {
    ".flac", ".mp3", ".ogg", ".oga", ".opus", ".m4a", ".mp4",
    ".wav", ".aiff", ".aif", ".ape", ".wv",
}

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "reproductor-flac"
LIBRARY_CACHE = CACHE_DIR / "library.json"
CACHE_VERSION = 1


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
        return self.artist or self.albumartist or tr("unknown_artist")

    @property
    def display_album(self) -> str:
        return self.album or tr("unknown_album")

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


_TRACK_FIELDS = tuple(field.name for field in fields(Track))


def _root_key(root: str | Path) -> str:
    try:
        return str(Path(root).expanduser().resolve())
    except OSError:
        return str(Path(root).expanduser())


def _track_data(track: Track) -> dict:
    return {name: getattr(track, name) for name in _TRACK_FIELDS}


def _track_from_data(data: object, path: str) -> Track | None:
    if not isinstance(data, dict):
        return None
    if any(name not in data for name in _TRACK_FIELDS):
        return None
    values = {name: data[name] for name in _TRACK_FIELDS if name != "path"}
    try:
        return Track(path=path, **values)
    except (TypeError, ValueError):
        return None


def _read_library_cache() -> dict:
    try:
        with LIBRARY_CACHE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return {}
    roots = data.get("roots")
    return roots if isinstance(roots, dict) else {}


def _write_library_cache(roots: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=str(CACHE_DIR), prefix="library-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {"version": CACHE_VERSION, "roots": roots},
                    handle,
                    ensure_ascii=False,
                )
            os.replace(temporary, LIBRARY_CACHE)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    except OSError:
        pass


def load_cached_library(root: str | Path) -> list[Track] | None:
    """Devuelve la biblioteca guardada en caché sin leer los archivos.

    Es instantánea: sirve para pintar la lista al abrir la aplicación
    mientras un escaneo en segundo plano comprueba si hay cambios.
    """
    key = _root_key(root)
    entry = _read_library_cache().get(key)
    if not isinstance(entry, dict):
        return None
    files = entry.get("files")
    if not isinstance(files, dict):
        return None
    base = Path(root).expanduser()
    tracks: list[Track] = []
    for relative, item in files.items():
        if not isinstance(item, dict):
            continue
        track = _track_from_data(item.get("track"), str(base / relative))
        if track is not None:
            tracks.append(track)
    tracks.sort(key=_sort_key)
    return tracks


def scan_library(root: str | Path, use_cache: bool = True) -> list[Track]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(tr("folder_not_found", root=root))

    key = _root_key(root)
    cached_roots = _read_library_cache() if use_cache else {}
    entry = cached_roots.get(key)
    cached_files = entry.get("files") if isinstance(entry, dict) else None
    if not isinstance(cached_files, dict):
        cached_files = {}

    tracks: list[Track] = []
    files: dict[str, dict] = {}
    for path in root.rglob("*"):
        try:
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:
                continue
            stat = path.stat()
        except OSError:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.name

        cached = cached_files.get(relative)
        track = None
        if (
            isinstance(cached, dict)
            and cached.get("mtime_ns") == stat.st_mtime_ns
            and cached.get("size") == stat.st_size
        ):
            track = _track_from_data(cached.get("track"), str(path))
        if track is None:
            try:
                track = read_track(path)
            except Exception:
                track = None
        if track is None:
            continue

        files[relative] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "track": _track_data(track),
        }
        tracks.append(track)

    tracks.sort(key=_sort_key)
    if use_cache and files != cached_files:
        cached_roots[key] = {"files": files}
        _write_library_cache(cached_roots)
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
    return tr("summary", tracks=len(tracks), albums=albums)


# --------------------------------------------------------------- letras
LRC_TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")
LRC_WORD_TAG = re.compile(r"<[^>]*>")
LRC_VERSION = re.compile(r"^v\d+:\s*", re.IGNORECASE)


def parse_lyrics(text: str, duration: float = 0.0) -> list[tuple[float, str]]:
    """Convierte una letra LRC en pares (segundo, línea).

    Acepta varias marcas de tiempo por línea, elimina las marcas de palabra
    ``<mm:ss.xx>`` y el prefijo ``v1:``. Si no hay marcas de tiempo reparte
    las líneas a lo largo de la duración para que la letra también avance.
    """
    if not text:
        return []

    entries: list[tuple[float, str]] = []
    plain: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        matches = list(LRC_TIMESTAMP.finditer(line))
        if not matches:
            if not line.startswith("["):
                plain.append(line)
            continue
        content = line[matches[-1].end():]
        content = LRC_WORD_TAG.sub("", content)
        content = LRC_VERSION.sub("", content).strip()
        if not content:
            continue
        for match in matches:
            minutes = int(match.group(1))
            seconds = float(match.group(2).replace(":", "."))
            entries.append((minutes * 60 + seconds, content))

    if entries:
        entries.sort(key=lambda item: item[0])
        cleaned: list[tuple[float, str]] = []
        for stamp, content in entries:
            if (
                cleaned
                and cleaned[-1][1] == content
                and abs(cleaned[-1][0] - stamp) < 0.01
            ):
                continue
            cleaned.append((stamp, content))
        return cleaned

    if not plain:
        return []
    lines = [
        LRC_VERSION.sub("", LRC_WORD_TAG.sub("", line)).strip()
        for line in plain
    ]
    lines = [line for line in lines if line]
    if not lines:
        return []
    total = duration if duration > 0 else len(lines) * 4.0
    step = total / len(lines)
    return [(index * step, line) for index, line in enumerate(lines)]


def _lyrics_from_tags(audio) -> str:
    tags = getattr(audio, "tags", None)
    if not tags:
        return ""
    try:
        keys = list(tags.keys())
    except Exception:
        return ""
    for key in keys:
        name = str(key).lower()
        if not (
            "lyrics" in name
            or "unsynced" in name
            or name in ("©lyr", "uslt")
        ):
            continue
        try:
            value = tags.get(key)
        except Exception:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if hasattr(value, "text"):
            value = value.text
        text = str(value).strip()
        if text:
            return text
    return ""


def get_lyrics(track: Track) -> list[tuple[float, str]]:
    """Devuelve la letra sincronizada de una pista, si existe.

    Primero busca un archivo ``.lrc`` junto a la canción y, si no hay,
    lee las etiquetas ``lyrics``/``unsyncedlyrics`` del propio archivo.
    """
    path = Path(track.path)
    texts: list[str] = []

    sidecar = path.with_suffix(".lrc")
    try:
        if sidecar.exists():
            texts.append(sidecar.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        pass

    if not texts:
        try:
            audio = _load(path)
        except Exception:
            audio = None
        if audio is not None:
            text = _lyrics_from_tags(audio)
            if text:
                texts.append(text)

    for text in texts:
        parsed = parse_lyrics(text, track.duration)
        if parsed:
            return parsed
    return []
