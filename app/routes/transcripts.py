from __future__ import annotations

import datetime as _dt
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from ..config import Settings
from ..deps import current_user, settings_dep
from ..fs import (
    UnsafePathError,
    filter_transcripts,
    list_transcripts,
    load_transcript,
    safe_transcript_path,
)
from ..rate_limit import limiter
from ..speaker import speaker_class, speaker_label
from ..srt import render_srt
from ..txt import render_txt

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


def _templates(request: Request):
    return request.app.state.templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _safe_name(name: str) -> str:
    # Audio basename: alnum, dot, dash, underscore, dot extension.
    if not re.match(r"^(?!\.)[A-Za-z0-9_.\-]{1,210}$", name):
        raise HTTPException(status_code=400, detail="bad transcript name")
    return name


def _parse_iso_date(s: str | None, *, end_of_day: bool = False) -> float | None:
    """Accept YYYY-MM-DD; return unix epoch (UTC). end_of_day adds 23:59:59."""
    if not s:
        return None
    try:
        d = _dt.date.fromisoformat(s.strip())
    except ValueError:
        return None
    t = _dt.time(23, 59, 59) if end_of_day else _dt.time(0, 0, 0)
    return _dt.datetime.combine(d, t, tzinfo=_dt.timezone.utc).timestamp()


_HIDE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-?]{1,32}$")


def _parse_hide(value: str) -> frozenset[str]:
    """Comma-separated speaker labels to hide. Unsafe / oversized tokens are
    silently dropped. Empty → empty set (no filtering)."""
    if not value:
        return frozenset()
    out: set[str] = set()
    for tok in value.split(","):
        tok = tok.strip()
        if tok and _HIDE_TOKEN_RE.match(tok):
            out.add(tok)
    return frozenset(out)


def _filter_segments(payload: dict, hide: frozenset[str]) -> dict:
    """Return a shallow-copied payload with `segments` filtered. Empty `hide`
    returns the original payload object (cheap no-op)."""
    if not hide:
        return payload
    segs = payload.get("segments") or []
    filtered = [s for s in segs if (s.get("speaker") or "?") not in hide]
    out = dict(payload)
    out["segments"] = filtered
    return out


def _unique_speakers(payload: dict) -> list[str]:
    """Sorted, deduplicated speaker labels appearing in the payload. Missing
    speaker is normalised to `'?'` so it shows up as a chip too."""
    seen: set[str] = set()
    for s in payload.get("segments") or []:
        spk = (s.get("speaker") or "").strip() or "?"
        seen.add(spk)
    return sorted(seen)


def _parse_opt_int(s: str, *, lo: int, hi: int, field: str) -> int | None:
    """Coerce a query-string value to an int. Empty string => None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        n = int(s)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc
    if not (lo <= n <= hi):
        raise HTTPException(
            status_code=400, detail=f"{field} out of range ({lo}..{hi})"
        )
    return n


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def list_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    q: str = Query(default="", max_length=200),
    lang: str = Query(default="", max_length=10),
    spk_min: str = Query(default="", max_length=4),
    spk_max: str = Query(default="", max_length=4),
    since: str = Query(default="", max_length=10),
    until: str = Query(default="", max_length=10),
):
    spk_min_n = _parse_opt_int(spk_min, lo=0, hi=64, field="spk_min")
    spk_max_n = _parse_opt_int(spk_max, lo=0, hi=64, field="spk_max")

    items = list_transcripts(settings)
    languages = sorted({t.language for t in items if t.language and t.language != "?"})
    items = filter_transcripts(
        items,
        q=q, lang=lang,
        speakers_min=spk_min_n, speakers_max=spk_max_n,
        since_epoch=_parse_iso_date(since),
        until_epoch=_parse_iso_date(until, end_of_day=True),
    )
    items.sort(key=lambda t: t.mtime, reverse=True)
    filters = {
        "q": q, "lang": lang,
        "spk_min": spk_min_n if spk_min_n is not None else "",
        "spk_max": spk_max_n if spk_max_n is not None else "",
        "since": since, "until": until,
    }
    any_filter_active = any(v not in ("", None) for v in filters.values())
    template = "transcripts/_list.html" if _is_htmx(request) else "transcripts/list.html"
    return _templates(request).TemplateResponse(
        request, template,
        {
            "items": items,
            "user": user,
            "page": "transcripts",
            "languages": languages,
            "filters": filters,
            "any_filter_active": any_filter_active,
        },
    )


@router.get("/{name}", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def detail_view(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    name = _safe_name(name)
    try:
        json_path = safe_transcript_path(settings.transcripts_dir, f"{name}.json")
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not json_path.is_file():
        raise HTTPException(status_code=404, detail="transcript not found")
    payload = load_transcript(json_path)
    return _templates(request).TemplateResponse(
        request, "transcripts/detail.html",
        {
            "name": name,
            "payload": payload,
            "speakers": _unique_speakers(payload),
            "speaker_class": speaker_class,
            "speaker_label": speaker_label,
            "user": user,
            "page": "transcripts",
        },
    )


@router.get("/{name}/download.{fmt}")
@limiter.limit("60/minute")
async def download(
    name: str,
    fmt: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    hide: str = Query(default="", max_length=400),
):
    """Generate the requested download.

    Formats:
        - `json` — full transcript JSON. Fast-path FileResponse when no `hide`
          filter is active; otherwise generated from the parsed payload.
        - `txt`  — plain prose (no timecodes). Speaker headers only at speaker
          change, suppressed entirely when there's <=1 unique speaker.
        - `txt-ts` — `[start - end] SPK: text` per line, mirrors the on-disk
          format the whisper service writes.
        - `srt`  — generated via `render_srt`.

    `hide=spkA,spkB,…` filters segments by speaker label before rendering."""
    name = _safe_name(name)
    fmt = fmt.lower()
    if fmt not in ("json", "txt", "txt-ts", "srt"):
        raise HTTPException(status_code=400, detail="unsupported format")
    hide_set = _parse_hide(hide)

    try:
        json_path = safe_transcript_path(settings.transcripts_dir, f"{name}.json")
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not json_path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    if fmt == "json" and not hide_set:
        # Cheap path: no filter → ship the raw file.
        return FileResponse(json_path, media_type="application/json",
                            filename=f"{name}.json")

    payload = load_transcript(json_path)
    filtered = _filter_segments(payload, hide_set)
    segments = filtered.get("segments") or []

    if fmt == "json":
        import json as _json
        body = _json.dumps(filtered, ensure_ascii=False, indent=2)
        return PlainTextResponse(
            body,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
        )

    if fmt == "txt":
        body = render_txt(segments, with_timecodes=False)
        return PlainTextResponse(
            body,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.txt"'},
        )

    if fmt == "txt-ts":
        body = render_txt(segments, with_timecodes=True)
        return PlainTextResponse(
            body,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.timecoded.txt"'},
        )

    # fmt == "srt"
    srt = render_srt(segments)
    return PlainTextResponse(
        srt,
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.srt"'},
    )
