"""Render whisper-service JSON segments to an SRT byte string."""
from __future__ import annotations

from io import StringIO
from typing import Iterable


def _srt_ts(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render_srt(segments: Iterable[dict]) -> str:
    """Render `segments` (list of {start_sec, end_sec, speaker, text, ...})
    into a UTF-8 SRT string. Speakers are prefixed as `SPEAKER:` when present
    and not "?" (unknown)."""
    buf = StringIO()
    for i, seg in enumerate(segments, start=1):
        start = float(seg.get("start_sec", 0.0))
        end = float(seg.get("end_sec", start))
        if end < start:
            end = start
        speaker = (seg.get("speaker") or "").strip()
        text = (seg.get("text") or "").strip()
        prefix = f"{speaker}: " if speaker and speaker != "?" else ""
        buf.write(f"{i}\n")
        buf.write(f"{_srt_ts(start)} --> {_srt_ts(end)}\n")
        buf.write(f"{prefix}{text}\n\n")
    return buf.getvalue()
