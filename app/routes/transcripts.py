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


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def list_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    q: str = Query(default="", max_length=200),
    lang: str = Query(default="", max_length=10),
    spk_min: int | None = Query(default=None, ge=0, le=64),
    spk_max: int | None = Query(default=None, ge=0, le=64),
    since: str = Query(default="", max_length=10),
    until: str = Query(default="", max_length=10),
):
    items = list_transcripts(settings)
    languages = sorted({t.language for t in items if t.language and t.language != "?"})
    items = filter_transcripts(
        items,
        q=q, lang=lang,
        speakers_min=spk_min, speakers_max=spk_max,
        since_epoch=_parse_iso_date(since),
        until_epoch=_parse_iso_date(until, end_of_day=True),
    )
    items.sort(key=lambda t: t.mtime, reverse=True)
    filters = {
        "q": q, "lang": lang,
        "spk_min": spk_min if spk_min is not None else "",
        "spk_max": spk_max if spk_max is not None else "",
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
):
    name = _safe_name(name)
    fmt = fmt.lower()
    if fmt not in ("json", "txt", "srt"):
        raise HTTPException(status_code=400, detail="unsupported format")

    if fmt == "json":
        try:
            path = safe_transcript_path(settings.transcripts_dir, f"{name}.json")
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type="application/json",
                            filename=f"{name}.json")

    if fmt == "txt":
        try:
            path = safe_transcript_path(settings.transcripts_dir, f"{name}.txt")
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type="text/plain; charset=utf-8",
                            filename=f"{name}.txt")

    # SRT: generated on the fly from the JSON segments.
    try:
        json_path = safe_transcript_path(settings.transcripts_dir, f"{name}.json")
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not json_path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    payload = load_transcript(json_path)
    srt = render_srt(payload.get("segments") or [])
    return PlainTextResponse(
        srt,
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.srt"'},
    )
