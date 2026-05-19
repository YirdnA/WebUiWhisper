"""Filesystem helpers — safe path resolution and listings.

Every path that enters this module from a request body is treated as
untrusted: validated against a strict regex, then resolved against the
configured base dir with `Path.resolve().relative_to(base)`. Any input that
escapes the base — symlink, `..`, absolute path — raises ValueError.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import Settings

# Filename allow list: alnum, dot, underscore, dash, space; bounded length.
# Extension must be in the configured allow list. Reject hidden files.
_NAME_RE = re.compile(r"^(?!\.)[A-Za-z0-9_.\-]{1,200}$")


class UnsafePathError(ValueError):
    pass


def validate_filename(name: str, settings: Settings) -> str:
    if not name or not _NAME_RE.match(name):
        raise UnsafePathError(f"unsafe filename: {name!r}")
    if Path(name).suffix.lower() not in settings.allowed_audio_exts:
        raise UnsafePathError(f"disallowed extension: {name!r}")
    return name


def safe_join(base: Path, name: str, settings: Settings) -> Path:
    """Resolve `name` under `base` rejecting traversal/symlink escapes."""
    safe_name = validate_filename(name, settings)
    candidate = (base / safe_name).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes base: {name!r}") from exc
    return candidate


def safe_transcript_path(base: Path, transcript_name: str) -> Path:
    """Same guard as safe_join but for `{audiofile}.{json|txt}` artifacts.
    Transcript artifacts must be the audio basename plus one of the allowed
    extensions plus `.json` or `.txt`.
    """
    if not transcript_name or "/" in transcript_name or "\\" in transcript_name:
        raise UnsafePathError(f"unsafe transcript name: {transcript_name!r}")
    if not re.match(r"^(?!\.)[A-Za-z0-9_.\-]{1,210}\.(json|txt)$", transcript_name):
        raise UnsafePathError(f"unsafe transcript name: {transcript_name!r}")
    candidate = (base / transcript_name).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes base: {transcript_name!r}") from exc
    return candidate


@dataclass(frozen=True)
class TranscriptSummary:
    name: str               # audio basename, e.g. "foo.flac"
    json_path: Path
    language: str
    duration_sec: float
    processing_sec: float
    speaker_count: int
    mtime: float
    segment_count: int
    model_used: str


def _speaker_count(segments: list[dict]) -> int:
    return len({s.get("speaker") for s in segments if s.get("speaker") not in (None, "")})


def filter_transcripts(
    items: list["TranscriptSummary"],
    *,
    q: str | None = None,
    lang: str | None = None,
    speakers_min: int | None = None,
    speakers_max: int | None = None,
    since_epoch: float | None = None,
    until_epoch: float | None = None,
    tag: str | None = None,
    settings: "Settings | None" = None,
) -> list["TranscriptSummary"]:
    """In-memory filter over already-loaded transcripts. Empty/None filters are no-ops.

    `tag` filters to transcripts whose enrich sidecar carries that hashtag.
    Requires `settings` to know where the sidecars live. Bad tag → empty out.
    """
    q_lower = q.lower().strip() if q else ""
    lang_norm = lang.strip().lower() if lang else ""
    tag_norm = (tag or "").strip().lower()
    out = []
    for t in items:
        if q_lower and q_lower not in t.name.lower():
            continue
        if lang_norm and t.language.lower() != lang_norm:
            continue
        if speakers_min is not None and t.speaker_count < speakers_min:
            continue
        if speakers_max is not None and t.speaker_count > speakers_max:
            continue
        if since_epoch is not None and t.mtime < since_epoch:
            continue
        if until_epoch is not None and t.mtime > until_epoch:
            continue
        if tag_norm:
            if settings is None:
                continue
            tags = _read_sidecar_hashtags(t.name, settings)
            if tag_norm not in {h.lower() for h in tags}:
                continue
        out.append(t)
    return out


def _read_sidecar_hashtags(name: str, settings) -> list[str]:
    """Cheap fetch of the hashtag list from a transcript's enrich sidecar.
    Returns [] if no sidecar or no hashtags. Reads the file each time —
    list pages are infrequent enough that an in-memory cache isn't worth
    the bookkeeping. Optimise later with a hashtag index if it gets slow.
    """
    candidates = [
        settings.transcripts_dir / f"{name}.enrich.json",
        settings.transcripts_dir / ARCHIVE_DIRNAME / f"{name}.enrich.json",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tags = (data.get("patterns") or {}).get("hashtags") or []
        return [str(t) for t in tags if t]
    return []


def transcript_hashtags(name: str, settings) -> list[str]:
    """Public helper used by list templates to render hashtag chips."""
    return _read_sidecar_hashtags(name, settings)


ARCHIVE_DIRNAME = "archive"


def _scan_transcripts_in(base: Path) -> list[TranscriptSummary]:
    """Scan a single directory for `*.json` transcripts. No recursion."""
    out: list[TranscriptSummary] = []
    if not base.is_dir():
        return out
    for entry in os.scandir(base):
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        # Skip versioned snapshots: foo.flac.json.v3
        if ".json.v" in entry.name:
            continue
        try:
            with open(entry.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or "segments" not in payload:
            continue
        segs = payload.get("segments") or []
        out.append(TranscriptSummary(
            name=entry.name[:-5],  # strip ".json"
            json_path=Path(entry.path),
            language=payload.get("language", "?"),
            duration_sec=float(payload.get("duration_sec", 0.0)),
            processing_sec=float(payload.get("processing_sec", 0.0)),
            speaker_count=_speaker_count(segs),
            mtime=entry.stat().st_mtime,
            segment_count=len(segs),
            model_used=payload.get("model_used", "?"),
        ))
    return out


def list_transcripts(settings: Settings) -> list[TranscriptSummary]:
    """Live transcripts only — the `archive/` subdir is skipped (it's a
    directory, not a `.json` file, so `entry.is_file()` already filters it,
    but the helper is explicit so a future structural change can't silently
    pull archived rows into the live tab)."""
    return _scan_transcripts_in(settings.transcripts_dir)


def list_archived_transcripts(settings: Settings) -> list[TranscriptSummary]:
    """Transcripts moved to the archive subdir. Same shape as
    `list_transcripts`; the caller decides which view to render."""
    archive_dir = settings.transcripts_dir / ARCHIVE_DIRNAME
    return _scan_transcripts_in(archive_dir)


def find_transcript_path(name: str, settings: Settings) -> tuple[Path, bool] | None:
    """Resolve `{name}.json` against the live dir, then the archive dir.
    Returns `(path, archived)` or None if it doesn't exist anywhere.

    `name` is the audio basename (e.g. `foo.flac`), not including `.json`.
    Caller is responsible for safe-naming via `safe_transcript_path` if the
    name came from a request."""
    live = settings.transcripts_dir / f"{name}.json"
    if live.is_file():
        return live, False
    archived = settings.transcripts_dir / ARCHIVE_DIRNAME / f"{name}.json"
    if archived.is_file():
        return archived, True
    return None


def transcript_artifact_paths(name: str, settings: Settings, *, archived: bool) -> list[Path]:
    """All on-disk files associated with `{name}` in the chosen tier:
    JSON, TXT, version snapshots, enrichment sidecars, display-name sidecar.
    Does NOT include the audio file (lives in `backup_dir`).

    Used by archive/unarchive/delete plumbing to move/remove a coherent set."""
    base = settings.transcripts_dir / ARCHIVE_DIRNAME if archived else settings.transcripts_dir
    out: list[Path] = []
    candidates = [
        base / f"{name}.json",
        base / f"{name}.txt",
        base / f"{name}.display_name",
        base / f"{name}.enrich.json",
        base / f"{name}.enrich.md",
        base / f"{name}.enrich.timecoded.md",
    ]
    for p in candidates:
        if p.is_file():
            out.append(p)
    out.extend(sorted(base.glob(f"{name}.json.v*")))
    return out


def list_queue(settings: Settings) -> list[dict]:
    """Files in /calls/ without a matching /transcripts/{name}.json.

    Sub-dir `6day_backup/` is excluded — those are already-processed backups.
    """
    calls = settings.calls_dir
    transcripts = settings.transcripts_dir
    if not calls.is_dir():
        return []
    out: list[dict] = []
    for entry in os.scandir(calls):
        if entry.is_dir():
            continue
        name = entry.name
        suffix = Path(name).suffix.lower()
        if suffix not in settings.allowed_audio_exts:
            continue
        sidecar = transcripts / f"{name}.json"
        if sidecar.is_file():
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        out.append({
            "name": name,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        })
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out


def load_transcript(json_path: Path) -> dict:
    with open(json_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ── Queue helpers (dead-letter + in-flight detection) ──────────────────────

FAILED_SUBDIR = "failed"
INFLIGHT_TAIL_BYTES = 64 * 1024


def list_failed(settings: Settings) -> list[dict]:
    """Files parked in `/calls/failed/` after exhausting the watcher's retry
    budget. Each entry includes the audio file's stat plus the parsed
    `{name}.error.txt` sidecar (first_fail, last_fail, attempts, last_error).
    Missing/malformed sidecars are tolerated."""
    failed_dir = settings.calls_dir / FAILED_SUBDIR
    if not failed_dir.is_dir():
        return []
    out: list[dict] = []
    for entry in os.scandir(failed_dir):
        if entry.is_dir():
            continue
        name = entry.name
        if not name or name.endswith(".error.txt"):
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in settings.allowed_audio_exts:
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        sidecar_path = failed_dir / f"{name}.error.txt"
        info = _parse_error_sidecar(sidecar_path)
        out.append({
            "name": name,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            **info,
        })
    out.sort(key=lambda r: r.get("last_fail") or r["mtime"], reverse=True)
    return out


def _parse_error_sidecar(path: Path) -> dict:
    """Read a `.error.txt` produced by `watcher.dead_letter`. Returns keys
    `first_fail`, `last_fail`, `attempts`, `last_error`. Missing/unparseable
    file falls back to placeholders."""
    fallback = {
        "first_fail": None,
        "last_fail": None,
        "attempts": None,
        "last_error": "(no sidecar)",
    }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return fallback
    out = dict(fallback)
    out["last_error"] = ""
    last_error_lines: list[str] = []
    capturing_error = False
    for line in text.splitlines():
        if capturing_error:
            last_error_lines.append(line)
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "first_fail":
            out["first_fail"] = val or None
        elif key == "last_fail":
            out["last_fail"] = val or None
        elif key == "attempts":
            try:
                out["attempts"] = int(val)
            except ValueError:
                out["attempts"] = None
        elif key == "last_error":
            last_error_lines.append(val)
            capturing_error = True
    out["last_error"] = "\n".join(last_error_lines).strip() or "(no sidecar)"
    return out


# Recognise these watcher.log line shapes.
#   2026-05-14 09:47:43,448 [INFO] watcher :: queued: foo.flac
#   2026-05-14 09:48:01,000 [INFO] watcher :: retry 1/3 (next in 60s): foo.flac
#   2026-05-14 09:50:11,123 [INFO] watcher :: ok: foo.flac model=... ...
#   2026-05-14 09:51:00,500 [ERROR] watcher :: transcription failed: foo.flac
#   2026-05-14 09:55:10,200 [ERROR] watcher :: DEAD-LETTER (after 3 attempts): foo.flac -> /calls/failed/foo.flac
_INFLIGHT_PATTERNS: tuple[tuple[str, str], ...] = (
    (" :: queued: ",                     "queued"),
    (" :: retry ",                       "retry"),       # "retry 1/3 (...): name"
    (" :: ok: ",                         "ok"),
    (" :: transcription failed: ",       "failed"),
    (" :: DEAD-LETTER ",                 "deadletter"),
    (" :: skip (already transcribed): ", "ok"),
)

_TERMINAL_STATES = {"ok", "failed", "deadletter"}


def _extract_filename(line: str, marker: str) -> str | None:
    """Pull the filename suffix from a watcher.log line whose `marker` we
    already matched. Handles each watcher log shape:

      "watcher :: queued: NAME"
      "watcher :: ok: NAME model=... ..."        — trailing key=value pairs
      "watcher :: skip (already transcribed): NAME"
      "watcher :: transcription failed: NAME"
      "watcher :: retry N/M (next in Xs): NAME"
      "watcher :: DEAD-LETTER (after N attempts): NAME -> /calls/failed/NAME"
    """
    idx = line.find(marker)
    if idx < 0:
        return None
    tail = line[idx + len(marker):]
    # Strip the destination half of DEAD-LETTER lines.
    if " -> " in tail:
        tail = tail.split(" -> ", 1)[0]
    # For markers that end with ": " the filename is the token after the
    # marker. For markers that don't (retry, DEAD-LETTER) the filename comes
    # after the last ": " in the remaining tail.
    if not marker.endswith(": "):
        if ": " in tail:
            tail = tail.rsplit(": ", 1)[1]
    tail = tail.strip()
    if not tail:
        return None
    # "ok: NAME model=... wait=... ..." — the filename is the first token.
    return tail.split()[0]


def read_inflight_state(log_path: Path, *, tail_bytes: int = INFLIGHT_TAIL_BYTES) -> dict[str, str]:
    """Read the last `tail_bytes` of `log_path` and return per-filename
    in-flight state. Only filenames whose latest event is non-terminal
    (queued / retry) are included. Bounded, cheap; safe to call on each
    HTMX poll. Returns `{}` on missing/unreadable file."""
    try:
        size = log_path.stat().st_size
    except OSError:
        return {}
    offset = max(0, size - tail_bytes)
    try:
        with open(log_path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read(size - offset)
    except OSError:
        return {}
    text = chunk.decode("utf-8", errors="replace")
    # Drop the leading partial line if we seeked into the middle of one.
    lines = text.splitlines()
    if offset > 0 and lines:
        lines = lines[1:]

    latest: dict[str, str] = {}
    for line in lines:
        for marker, state in _INFLIGHT_PATTERNS:
            if marker in line:
                name = _extract_filename(line, marker)
                if name:
                    latest[name] = state
                break
    return {n: s for n, s in latest.items() if s not in _TERMINAL_STATES}
