"""Helpers for the inline transcript editor.

Versioning scheme:
- Live transcript:    {name}.json + {name}.txt
- Past versions:      {name}.json.v1, {name}.json.v2, ...   (JSON only)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"\.v(\d+)$")


def next_version(transcripts_dir: Path, name: str) -> int:
    """Highest existing .v{N} suffix for {name}.json, plus one. Starts at 1."""
    base = transcripts_dir / f"{name}.json"
    max_v = 0
    for entry in transcripts_dir.glob(f"{base.name}.v*"):
        m = _VERSION_RE.search(entry.name)
        if not m:
            continue
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        max_v = max(max_v, n)
    return max_v + 1


def archive_current(transcripts_dir: Path, name: str) -> Path | None:
    """Copy the live JSON to a fresh .v{N} alongside. Returns the new path or None."""
    live = transcripts_dir / f"{name}.json"
    if not live.is_file():
        return None
    v = next_version(transcripts_dir, name)
    dst = transcripts_dir / f"{name}.json.v{v}"
    shutil.copy2(live, dst)
    return dst


def _hhmmss(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def render_txt(payload: dict[str, Any]) -> str:
    """Regenerate the {name}.txt companion in the same format the whisper
    service writes (see /opt/whisper/app/output.py)."""
    lines: list[str] = []
    lines.append(f"# {payload.get('source_file', '?')}")
    lines.append(
        f"# language={payload.get('language', '?')} "
        f"({payload.get('language_confidence', 0):.2f}) "
        f"duration={payload.get('duration_sec', 0):.1f}s "
        f"processing={payload.get('processing_sec', 0):.1f}s "
        f"model={payload.get('model_used', '?')}"
    )
    lines.append("")
    for seg in payload.get("segments", []):
        start = seg.get("start_time") or _hhmmss(float(seg.get("start_sec", 0.0)))
        end = seg.get("end_time") or _hhmmss(float(seg.get("end_sec", 0.0)))
        speaker = seg.get("speaker") or "?"
        text = seg.get("text") or ""
        lines.append(f"[{start} - {end}] {speaker}: {text}")
    return "\n".join(lines) + "\n"


def write_live(transcripts_dir: Path, name: str, payload: dict[str, Any]) -> None:
    """Overwrite the live {name}.json and {name}.txt."""
    json_path = transcripts_dir / f"{name}.json"
    txt_path = transcripts_dir / f"{name}.txt"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    txt_path.write_text(render_txt(payload), encoding="utf-8")


def apply_edits(
    payload: dict[str, Any],
    new_speakers: list[str],
    new_texts: list[str],
) -> dict[str, Any]:
    """Replace `speaker` and `text` per-segment by parallel lists. Existing
    timings, language, duration etc. are preserved."""
    segments = payload.get("segments", [])
    if len(new_speakers) != len(segments) or len(new_texts) != len(segments):
        raise ValueError(
            f"edit length mismatch: segments={len(segments)} "
            f"speakers={len(new_speakers)} texts={len(new_texts)}"
        )
    updated = []
    for seg, sp, tx in zip(segments, new_speakers, new_texts):
        new_seg = dict(seg)
        new_seg["speaker"] = sp.strip() or "?"
        new_seg["text"] = tx.strip()
        updated.append(new_seg)
    payload["segments"] = updated
    return payload
