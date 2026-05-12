"""Bulk delete / archive on the transcripts list view."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..rate_limit import limiter

router = APIRouter(prefix="/transcripts", tags=["bulk"])

log = logging.getLogger("webuiwhisper.bulk")

_NAME_RE = re.compile(r"^(?!\.)[A-Za-z0-9_.\-]{1,210}$")
_ARCHIVE_DIRNAME = "archive"
ALLOWED_ACTIONS = {"delete", "archive"}


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"bad transcript name: {name!r}")
    return name


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "-"
    return request.client.host


def _related_paths(transcripts_dir: Path, name: str) -> list[Path]:
    """All files we own for this transcript: live JSON+TXT plus any versions."""
    out: list[Path] = []
    json_live = transcripts_dir / f"{name}.json"
    txt_live = transcripts_dir / f"{name}.txt"
    if json_live.is_file():
        out.append(json_live)
    if txt_live.is_file():
        out.append(txt_live)
    out.extend(sorted(transcripts_dir.glob(f"{name}.json.v*")))
    return out


def _within(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _delete_one(name: str, settings: Settings) -> dict:
    """Returns counts of files removed."""
    transcripts_dir = settings.transcripts_dir
    backup_dir = settings.backup_dir

    removed_t = 0
    for p in _related_paths(transcripts_dir, name):
        if _within(p, transcripts_dir):
            try:
                p.unlink()
                removed_t += 1
            except OSError as exc:
                log.warning("delete failed %s: %s", p, exc)

    removed_b = 0
    audio_in_backup = backup_dir / name
    if audio_in_backup.is_file() and _within(audio_in_backup, backup_dir):
        try:
            audio_in_backup.unlink()
            removed_b = 1
        except OSError as exc:
            log.warning("backup delete failed %s: %s", audio_in_backup, exc)

    return {"transcripts_removed": removed_t, "audio_removed": removed_b}


def _archive_one(name: str, settings: Settings) -> dict:
    """Move transcripts + audio backup to {transcripts_dir}/archive/."""
    transcripts_dir = settings.transcripts_dir
    backup_dir = settings.backup_dir
    archive_dir = transcripts_dir / _ARCHIVE_DIRNAME
    archive_dir.mkdir(parents=True, exist_ok=True)

    moved_t = 0
    for p in _related_paths(transcripts_dir, name):
        if not _within(p, transcripts_dir):
            continue
        dst = archive_dir / p.name
        if dst.exists():
            log.warning("archive target exists, skipping %s", dst)
            continue
        try:
            shutil.move(str(p), str(dst))
            moved_t += 1
        except OSError as exc:
            log.warning("archive move failed %s -> %s: %s", p, dst, exc)

    moved_b = 0
    audio = backup_dir / name
    if audio.is_file() and _within(audio, backup_dir):
        audio_archive = archive_dir / "audio"
        audio_archive.mkdir(parents=True, exist_ok=True)
        dst = audio_archive / audio.name
        if not dst.exists():
            try:
                shutil.move(str(audio), str(dst))
                moved_b = 1
            except OSError as exc:
                log.warning("archive audio move failed %s -> %s: %s", audio, dst, exc)

    return {"transcripts_archived": moved_t, "audio_archived": moved_b}


@router.post("/bulk")
@limiter.limit("10/minute")
async def bulk(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    form = await request.form()
    action = str(form.get("action", "")).lower()
    if action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"unknown action: {action!r}")

    names = [str(v) for v in form.getlist("names")]
    safe_names = [_safe_name(n) for n in names if n]
    if not safe_names:
        return RedirectResponse(url="/transcripts", status_code=303)

    ip = _client_ip(request)
    results: list[dict] = []
    for name in safe_names:
        try:
            if action == "delete":
                res = _delete_one(name, settings)
            else:
                res = _archive_one(name, settings)
        except Exception as exc:
            log.exception("bulk %s failed for %s", action, name)
            await audit_record(
                f"bulk-{action}-fail", user=user, ip=ip, target=name, ok=False,
                extra={"err": str(exc)},
            )
            results.append({"name": name, "error": str(exc)})
            continue
        results.append({"name": name, **res})
        await audit_record(
            f"bulk-{action}", user=user, ip=ip, target=name, ok=True, extra=res,
        )

    return RedirectResponse(
        url=f"/transcripts?bulk_done={action}&n={len(safe_names)}",
        status_code=303,
    )
