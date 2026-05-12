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
) -> list["TranscriptSummary"]:
    """In-memory filter over already-loaded transcripts. Empty/None filters are no-ops."""
    q_lower = q.lower().strip() if q else ""
    lang_norm = lang.strip().lower() if lang else ""
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
        out.append(t)
    return out


def list_transcripts(settings: Settings) -> list[TranscriptSummary]:
    out: list[TranscriptSummary] = []
    base = settings.transcripts_dir
    if not base.is_dir():
        return out
    for entry in os.scandir(base):
        if not entry.is_file() or not entry.name.endswith(".json"):
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
