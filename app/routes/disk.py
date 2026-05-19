"""Disk dashboard: sizes of the audio + transcripts dirs plus a per-day
transcript histogram for the last 30 days."""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..config import Settings
from ..deps import current_user, settings_dep
from ..fs import list_transcripts
from ..rate_limit import limiter

router = APIRouter(prefix="/disk", tags=["disk"])

# Rendered in this order on the page.
_DIRS_RELATIVE = [
    ("Inbox",              "calls_dir",      None),
    ("6-day backup",       "calls_dir",      "6day_backup"),
    ("Dead-letter",        "calls_dir",      "failed"),
    ("Transcripts",        "transcripts_dir", None),
]

HISTOGRAM_DAYS = 30


def _templates(request: Request):
    return request.app.state.templates


def _dir_size(path: Path) -> tuple[int, int]:
    """Recursive (size_bytes, file_count) under `path`. Symlinks not followed.
    Returns (0, 0) on missing path or any OSError (logged at caller's discretion)."""
    total = 0
    count = 0
    if not path.is_dir():
        return 0, 0
    stack: list[Path] = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            count += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, count


def _human(n: int) -> str:
    """Bytes → short human-readable string. 1 KiB = 1024 B."""
    if n < 1024:
        return f"{n} B"
    units = ["KiB", "MiB", "GiB", "TiB"]
    x = float(n) / 1024.0
    for u in units:
        if x < 1024.0 or u == units[-1]:
            return f"{x:.1f} {u}"
        x /= 1024.0
    return f"{n} B"


def _bucket_by_day(summaries, *, days: int = HISTOGRAM_DAYS) -> list[tuple[_dt.date, int]]:
    """Return `days` (date, count) pairs ending at today (UTC), oldest first.

    `summaries` is any iterable yielding objects with a `.mtime` float."""
    today = _dt.datetime.now(tz=_dt.timezone.utc).date()
    counts: dict[_dt.date, int] = {}
    for s in summaries:
        try:
            day = _dt.datetime.fromtimestamp(s.mtime, tz=_dt.timezone.utc).date()
        except (OSError, OverflowError, ValueError):
            continue
        if (today - day).days >= days or day > today:
            continue
        counts[day] = counts.get(day, 0) + 1
    out = []
    for i in range(days - 1, -1, -1):
        d = today - _dt.timedelta(days=i)
        out.append((d, counts.get(d, 0)))
    return out


@router.get("", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def disk_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    rows = []
    for label, attr, sub in _DIRS_RELATIVE:
        base = getattr(settings, attr)
        target = base / sub if sub else base
        size, count = _dir_size(target)
        rows.append({
            "label": label,
            "path": str(target),
            "size": size,
            "human": _human(size),
            "files": count,
        })

    summaries = list_transcripts(settings)
    histogram = _bucket_by_day(summaries)
    hist_max = max((c for _, c in histogram), default=0)

    return _templates(request).TemplateResponse(
        request, "disk/index.html",
        {
            "user": user,
            "page": "disk",
            "rows": rows,
            "histogram": histogram,
            "hist_max": hist_max,
            "total_transcripts": len(summaries),
        },
    )
