"""POST /rediarize — kicks off a re-diarization on the upstream whisper service.

The call can take minutes to hours. To avoid blocking the request through
Apache's ProxyTimeout, we fire-and-forget via asyncio.create_task and
record the outcome in the audit log. The user watches progress on /queue
(SSE log tail) and reloads the detail page when done.
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..audit import record as audit_record
from ..deps import current_user, require_csrf, whisper_client_dep
from ..rate_limit import limiter
from ..whisper_client import WhisperClient, WhisperClientError

router = APIRouter(prefix="/rediarize", tags=["rediarize"])

log = logging.getLogger("webuiwhisper.rediarize")


def _safe_name(name: str) -> str:
    if not re.match(r"^(?!\.)[A-Za-z0-9_.\-]{1,210}$", name):
        raise HTTPException(status_code=400, detail="bad name")
    return name


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "-"
    return request.client.host


async def _run(client: WhisperClient, name: str, hints: dict[str, int | None],
               user: str, ip: str) -> None:
    log.info("rediarize started user=%s target=%s hints=%s", user, name, hints)
    await audit_record(
        "rediarize-start", user=user, ip=ip, target=name, ok=True, extra=hints,
    )
    try:
        result = await client.rediarize(
            name,
            num_speakers=hints.get("num_speakers"),
            min_speakers=hints.get("min_speakers"),
            max_speakers=hints.get("max_speakers"),
        )
        speakers = len({s.get("speaker") for s in result.get("segments", [])})
        log.info("rediarize ok user=%s target=%s speakers=%d", user, name, speakers)
        await audit_record(
            "rediarize-ok", user=user, ip=ip, target=name, ok=True,
            extra={"speakers": speakers},
        )
    except WhisperClientError as exc:
        log.error("rediarize failed user=%s target=%s err=%s", user, name, exc)
        await audit_record(
            "rediarize-fail", user=user, ip=ip, target=name, ok=False,
            extra={"err": str(exc)},
        )


@router.post("")
@limiter.limit("5/minute")
async def submit(
    request: Request,
    user: str = Depends(current_user),
    client: WhisperClient = Depends(whisper_client_dep),
    _: None = Depends(require_csrf),
):
    form = await request.form()
    name = _safe_name(str(form.get("name", "")))

    def _parse_int(v: str | None, lo: int, hi: int) -> int | None:
        if not v:
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        if lo <= n <= hi:
            return n
        return None

    hints = {
        "num_speakers": _parse_int(str(form.get("num_speakers", "")), 1, 32),
        "min_speakers": _parse_int(str(form.get("min_speakers", "")), 1, 32),
        "max_speakers": _parse_int(str(form.get("max_speakers", "")), 1, 32),
    }

    # Fire-and-forget; the upstream call may take hours.
    asyncio.create_task(_run(client, name, hints, user, _client_ip(request)))

    return RedirectResponse(
        url=f"/transcripts/{name}?rediar=queued", status_code=303,
    )
