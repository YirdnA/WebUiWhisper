"""Per-transcript display-name sidecar.

The canonical `{name}.json` is never mutated. A small sibling file
`{name}.display_name` holds a single UTF-8 line — the human-friendly name
the UI surfaces in headers, list cells, queue rows, and download filenames.

Read is cheap (LRU cache keyed by `(path, mtime)`). Write is atomic
(`.tmp` → `os.replace`). Clear is `unlink(missing_ok=True)`.

The full read/auto-suggest/rename UI lives in D6; D7 needs the read +
sanitize helpers to land first because download `Content-Disposition`
already depends on display-name.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from .config import Settings
from .fs import ARCHIVE_DIRNAME

DISPLAY_NAME_SUFFIX = ".display_name"

_MAX_LEN = 200


def _sidecar_path(name: str, settings: Settings) -> Path | None:
    """Resolve the sidecar path against the live or archived tier.
    Returns None for invalid names.
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    base = settings.transcripts_dir
    live = base / f"{name}{DISPLAY_NAME_SUFFIX}"
    if live.is_file():
        return live
    archived = base / ARCHIVE_DIRNAME / f"{name}{DISPLAY_NAME_SUFFIX}"
    if archived.is_file():
        return archived
    # No file yet — return the live-tier path as the default write target.
    return live


def _read_text_for_cache(path_str: str, mtime: float) -> str:
    try:
        return Path(path_str).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


_read_cached = lru_cache(maxsize=512)(_read_text_for_cache)


def read_display_name(name: str, settings: Settings) -> str | None:
    """Return the display name for `name`, or None if no sidecar is set."""
    path = _sidecar_path(name, settings)
    if path is None:
        return None
    if not path.is_file():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    text = _read_cached(str(path), mtime)
    return text or None


def _resolve_for_write(name: str, settings: Settings) -> Path | None:
    """Pick the right tier to write the sidecar in — match where the JSON
    currently lives. Falls back to the live dir if no JSON found (callers
    typically guard with `find_transcript_path` before reaching this)."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    live_json = settings.transcripts_dir / f"{name}.json"
    if live_json.is_file():
        return settings.transcripts_dir / f"{name}{DISPLAY_NAME_SUFFIX}"
    archived_json = settings.transcripts_dir / ARCHIVE_DIRNAME / f"{name}.json"
    if archived_json.is_file():
        return settings.transcripts_dir / ARCHIVE_DIRNAME / f"{name}{DISPLAY_NAME_SUFFIX}"
    # No JSON anywhere — let the caller decide. Returning the live path
    # avoids surprises but a strict caller should 404 before here.
    return settings.transcripts_dir / f"{name}{DISPLAY_NAME_SUFFIX}"


def write_display_name(name: str, value: str, settings: Settings) -> None:
    """Atomic write. Empty/whitespace value clears instead of writing."""
    if not value or not value.strip():
        clear_display_name(name, settings)
        return
    text = value.strip()[:_MAX_LEN]
    path = _resolve_for_write(name, settings)
    if path is None:
        raise ValueError(f"invalid name: {name!r}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    os.replace(tmp, path)


def clear_display_name(name: str, settings: Settings) -> None:
    """Remove the sidecar so the UI falls back to the default pretty name.
    Looks in both live and archive tiers."""
    for base in (settings.transcripts_dir, settings.transcripts_dir / ARCHIVE_DIRNAME):
        p = base / f"{name}{DISPLAY_NAME_SUFFIX}"
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


# ── filename sanitisation ────────────────────────────────────────────────────

# Minimal Cyrillic → Latin transliteration covering Ukrainian + Russian.
# Reuses a single map; characters not in the map (e.g. emoji, CJK) are
# dropped by the regex pass below.
_TRANSLIT: dict[str, str] = {
    # Russian
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # Ukrainian-specific additions
    "є": "ye", "і": "i", "ї": "yi", "ґ": "g",
}


def _translit(s: str) -> str:
    out: list[str] = []
    for ch in s:
        lower = ch.lower()
        if lower in _TRANSLIT:
            mapped = _TRANSLIT[lower]
            out.append(mapped.upper() if ch.isupper() else mapped)
        else:
            out.append(ch)
    return "".join(out)


_FILENAME_KEEP = re.compile(r"[^A-Za-z0-9 _.\-()]+")
_MULTI_WS = re.compile(r"\s+")


def sanitize_filename_ascii(s: str) -> str:
    """Return an ASCII-safe filename body (no extension) for use in
    `Content-Disposition: filename="..."`. Empty result is allowed; the
    caller should fall back to a technical name in that case.

    Pipeline: transliterate Cyrillic → drop anything outside [A-Za-z0-9 _.-()]
    → collapse whitespace → trim → truncate to 100 chars.
    """
    if not s:
        return ""
    s = _translit(s)
    s = _FILENAME_KEEP.sub("", s)
    s = _MULTI_WS.sub(" ", s).strip(" .")
    return s[:100]
