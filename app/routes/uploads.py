from __future__ import annotations

import datetime as dt
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import magic
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..fs import UnsafePathError
from ..rate_limit import limiter

router = APIRouter(prefix="/upload", tags=["upload"])

log = logging.getLogger("webuiwhisper.uploads")

# python-magic returns MIME types like "audio/wav", "audio/mpeg", "audio/flac",
# "audio/ogg", "audio/mp4", "video/webm", "video/mp4". We accept audio/* and
# the two video containers commonly used for audio-only recordings.
ALLOWED_MIMES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/x-flac",
    "audio/ogg", "audio/vorbis", "audio/opus",
    "audio/mp4", "audio/x-m4a",
    "audio/webm",
    "video/mp4", "video/webm",
    "application/octet-stream",  # last-resort; we already checked the extension
}

_SAFE_STEM = re.compile(r"[^A-Za-z0-9_\-]+")

# Models the whisper image has baked in. Keep in sync with the upstream
# /models response; the upload form mirrors this list.
ALLOWED_MODELS = ("large-v3", "large-v3-turbo")


def _sanitize_stem(stem: str) -> str:
    s = _SAFE_STEM.sub("_", stem).strip("_")
    return s[:80] or "audio"


def _timestamped_name(orig: str, settings: Settings) -> str:
    src = Path(orig)
    ext = src.suffix.lower()
    if ext not in settings.allowed_audio_exts:
        raise UnsafePathError(f"disallowed extension: {orig!r}")
    stem = _sanitize_stem(src.stem)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return f"{stem}_{stamp}{ext}"


@router.get("", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def upload_form(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    return request.app.state.templates.TemplateResponse(
        request, "uploads/form.html",
        {"user": user, "page": "upload",
         "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
         "allowed_models": ALLOWED_MODELS},
    )


@router.post("", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def upload_submit(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="no filename")

    # Optional model hint. Empty / "auto" → no sidecar, watcher uses its env default.
    form = await request.form()
    model_hint = str(form.get("model", "")).strip()
    if model_hint and model_hint != "auto" and model_hint not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"unknown model: {model_hint!r}")
    if model_hint == "auto":
        model_hint = ""

    try:
        target_name = _timestamped_name(file.filename, settings)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Stream upload to a temp file with byte cap; sniff magic; then move into
    # /calls/. tmpfile is in the calls dir so the rename is atomic and stays
    # on the same filesystem.
    settings.calls_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".upload-", dir=str(settings.calls_dir))
    total = 0
    try:
        with open(fd, "wb") as out_fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"upload exceeds {settings.max_upload_bytes} bytes",
                    )
                out_fh.write(chunk)

        # Magic-byte sniff
        mime = magic.from_file(tmp_path, mime=True)
        if mime not in ALLOWED_MIMES:
            log.warning("upload rejected mime=%s name=%s user=%s", mime, target_name, user)
            await audit_record(
                "upload-rejected", user=user, ip=_client_ip(request),
                target=target_name, ok=False, extra={"mime": mime},
            )
            raise HTTPException(status_code=415,
                                detail=f"file content rejected (mime={mime})")

        final_path = settings.calls_dir / target_name
        if final_path.exists():
            # Extremely unlikely with the second-precision timestamp suffix; bail.
            raise HTTPException(status_code=409, detail="target already exists")
        shutil.move(tmp_path, final_path)
        tmp_path = None

        # Write the model hint sidecar BEFORE the audio is visible to the
        # watcher — but `shutil.move` above already revealed it. The watcher's
        # `wait_until_stable` debounce (3s) gives us a small window; write the
        # sidecar promptly so the watcher sees both.
        if model_hint:
            sidecar = settings.calls_dir / f"{target_name}.model"
            try:
                sidecar.write_text(model_hint + "\n", encoding="utf-8")
            except OSError as exc:
                log.warning("model sidecar write failed %s: %s", sidecar, exc)

        await audit_record(
            "upload", user=user, ip=_client_ip(request),
            target=target_name, ok=True,
            extra={"bytes": total, "mime": mime, "model": model_hint or "auto"},
        )
    finally:
        if tmp_path and Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

    return RedirectResponse(url="/queue", status_code=303)


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "-"
    return request.client.host
