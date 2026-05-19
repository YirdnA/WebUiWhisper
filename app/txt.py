"""Render whisper-service JSON segments to a plain-text or timecoded-text
download. Mirrors `app/srt.py`'s shape: pure functions, deterministic output."""
from __future__ import annotations

from io import StringIO
from typing import Iterable


def _hhmmss_ms(sec: float) -> str:
    """Mirror the on-disk `{name}.txt` format produced by the whisper service:
    `HH:MM:SS.mmm`. Used as a fallback when a segment lacks a `start_time` or
    `end_time` string."""
    if sec < 0:
        sec = 0.0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _seg_time(seg: dict, key_str: str, key_sec: str) -> str:
    val = seg.get(key_str)
    if isinstance(val, str) and val.strip():
        return val.strip()
    try:
        return _hhmmss_ms(float(seg.get(key_sec, 0.0)))
    except (TypeError, ValueError):
        return _hhmmss_ms(0.0)


def _speaker_or_q(seg: dict) -> str:
    s = (seg.get("speaker") or "").strip()
    return s if s else "?"


def render_txt(segments: Iterable[dict], *, with_timecodes: bool) -> str:
    """Render segments as a UTF-8 text string.

    - `with_timecodes=True`: `[start - end] SPK: text` on one line per segment.
      Same shape the whisper service writes to `{name}.txt`.
    - `with_timecodes=False`: clean prose — text only, joined with newlines.
      A `SPEAKER:` header line is emitted on speaker change. If the whole
      transcript has at most one unique non-empty speaker (e.g. all `"?"` or
      all `"A"`), speaker headers are suppressed entirely.

    Empty input → empty string. Always ends with a single trailing newline
    when non-empty.
    """
    segs = list(segments)
    if not segs:
        return ""

    if with_timecodes:
        buf = StringIO()
        for seg in segs:
            start = _seg_time(seg, "start_time", "start_sec")
            end = _seg_time(seg, "end_time", "end_sec")
            spk = _speaker_or_q(seg)
            text = (seg.get("text") or "").strip()
            buf.write(f"[{start} - {end}] {spk}: {text}\n")
        return buf.getvalue()

    # Plain: text-only, with speaker headers only at changes if there's
    # more than one unique speaker.
    speakers_seen = {_speaker_or_q(s) for s in segs}
    show_speakers = len(speakers_seen) > 1

    buf = StringIO()
    last_speaker: str | None = None
    for seg in segs:
        spk = _speaker_or_q(seg)
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if show_speakers and spk != last_speaker:
            if last_speaker is not None:
                buf.write("\n")  # blank line between speaker blocks
            buf.write(f"{spk}:\n")
            last_speaker = spk
        buf.write(f"{text}\n")
    return buf.getvalue()
