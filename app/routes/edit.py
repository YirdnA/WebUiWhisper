"""Inline transcript editor: GET form, POST save with versioned backup."""
from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..editor import apply_edits, archive_current, write_live
from ..fs import UnsafePathError, load_transcript, safe_transcript_path
from ..rate_limit import limiter
from ..speaker import speaker_class, speaker_label

router = APIRouter(prefix="/transcripts", tags=["edit"])

log = logging.getLogger("webuiwhisper.edit")


def _safe_name(name: str) -> str:
    if not re.match(r"^(?!\.)[A-Za-z0-9_.\-]{1,210}$", name):
        raise HTTPException(status_code=400, detail="bad transcript name")
    return name


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "-"
    return request.client.host


@router.get("/{name}/edit", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def edit_form(
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
    return request.app.state.templates.TemplateResponse(
        request, "transcripts/edit.html",
        {
            "name": name,
            "payload": payload,
            "speaker_class": speaker_class,
            "speaker_label": speaker_label,
            "user": user,
            "page": "transcripts",
        },
    )


@router.post("/{name}/edit", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def edit_submit(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    name = _safe_name(name)
    form = await request.form()

    try:
        json_path = safe_transcript_path(settings.transcripts_dir, f"{name}.json")
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not json_path.is_file():
        raise HTTPException(status_code=404, detail="transcript not found")

    payload = load_transcript(json_path)
    n = len(payload.get("segments", []))

    new_speakers = [str(form.get(f"speaker_{i}", "")) for i in range(n)]
    new_texts = [str(form.get(f"text_{i}", "")) for i in range(n)]

    try:
        payload = apply_edits(payload, new_speakers, new_texts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload["edited_at"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["edited_by"] = user

    backup_path = archive_current(settings.transcripts_dir, name)
    write_live(settings.transcripts_dir, name, payload)

    version = 0
    if backup_path is not None:
        m = re.search(r"\.v(\d+)$", backup_path.name)
        if m:
            version = int(m.group(1))

    await audit_record(
        "transcript-edit", user=user, ip=_client_ip(request),
        target=name, ok=True,
        extra={"backup_version": version, "segments": n},
    )

    return RedirectResponse(
        url=f"/transcripts/{name}?saved=1&v={version}", status_code=303,
    )
