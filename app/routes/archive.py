"""Archive workflow: archive / unarchive / single-delete.

Safety contract:
- **Delete is only available for archived transcripts.** The route also
  requires a typed-confirmation matching the archived file's stem in the
  POST body — even if the client-side modal is bypassed, the server
  re-validates.
- Archive/unarchive are reversible MOVES inside `transcripts_dir`. No
  content bytes are mutated.
- Every action records to `app/audit.py::record(...)`.
- The audio file in `/calls/6day_backup/` is untouched (the watcher owns
  the 6-day retention; archiving a transcript is independent).
"""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..fs import (
    ARCHIVE_DIRNAME,
    find_transcript_path,
    transcript_artifact_paths,
)
from ..rate_limit import limiter

router = APIRouter(prefix="/transcripts", tags=["archive"])

log = logging.getLogger("webuiwhisper.archive")

_NAME_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_.\-, ()]{1,210}$")


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"bad transcript name: {name!r}")
    return name


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "-"


def _ensure_archive_dir(settings: Settings) -> Path:
    p = settings.transcripts_dir / ARCHIVE_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _move_set(paths: list[Path], dst_dir: Path) -> int:
    """Move each path into dst_dir. Returns count moved. Atomic per-file via
    `os.replace` (shutil.move falls back to copy+remove only on cross-FS)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in paths:
        target = dst_dir / src.name
        if target.exists():
            log.warning("archive target exists, skipping %s", target)
            continue
        try:
            shutil.move(str(src), str(target))
            moved += 1
        except OSError as exc:
            log.warning("move failed %s -> %s: %s", src, target, exc)
    return moved


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── archive ─────────────────────────────────────────────────────────────────


@router.post("/{name}/archive")
@limiter.limit("30/minute")
async def archive_one(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")
    _, already_archived = found
    if already_archived:
        return RedirectResponse(
            url=f"/transcripts?view=archived&did=archive&name={name}",
            status_code=303,
        )
    paths = transcript_artifact_paths(name, settings, archived=False)
    dst = _ensure_archive_dir(settings)
    moved = _move_set(paths, dst)
    await audit_record(
        "archive", user=user, ip=_client_ip(request),
        target=name, ok=True, extra={"files_moved": moved},
    )
    return RedirectResponse(
        url=f"/transcripts?did=archive&name={name}",
        status_code=303,
    )


# ── unarchive (restore) ─────────────────────────────────────────────────────


@router.post("/{name}/unarchive")
@limiter.limit("30/minute")
async def unarchive_one(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")
    _, archived = found
    if not archived:
        return RedirectResponse(
            url=f"/transcripts?did=unarchive&name={name}",
            status_code=303,
        )
    paths = transcript_artifact_paths(name, settings, archived=True)
    moved = _move_set(paths, settings.transcripts_dir)
    await audit_record(
        "unarchive", user=user, ip=_client_ip(request),
        target=name, ok=True, extra={"files_moved": moved},
    )
    return RedirectResponse(
        url=f"/transcripts?did=unarchive&name={name}",
        status_code=303,
    )


# ── delete (only when archived, requires typed-confirm) ─────────────────────


@router.post("/{name}/delete")
@limiter.limit("10/minute")
async def delete_one(
    name: str,
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
    confirm: str = Form(default=""),
):
    """Hard-delete an archived transcript.

    Requires:
    - target name resolves to a file inside `archive/` (i.e. already archived)
    - POST body has `confirm` exactly matching the stripped basename
      (`{name}` minus its audio extension), so a sloppy client can't
      delete by accident.
    """
    name = _safe_name(name)
    found = find_transcript_path(name, settings)
    if not found:
        raise HTTPException(status_code=404, detail="transcript not found")
    _, archived = found
    if not archived:
        raise HTTPException(
            status_code=400,
            detail="transcript must be archived before it can be deleted",
        )

    # Match the modal contract: type the basename without extension to confirm.
    stem = Path(name).stem
    if confirm.strip() != stem:
        raise HTTPException(
            status_code=400,
            detail="confirmation text did not match",
        )

    paths = transcript_artifact_paths(name, settings, archived=True)
    sha = ""
    json_path = settings.transcripts_dir / ARCHIVE_DIRNAME / f"{name}.json"
    if json_path.is_file():
        try:
            sha = _sha256_of_file(json_path)
        except OSError:
            sha = ""

    removed: list[str] = []
    for p in paths:
        try:
            p.unlink()
            removed.append(p.name)
        except OSError as exc:
            log.warning("delete failed %s: %s", p, exc)

    await audit_record(
        "delete", user=user, ip=_client_ip(request),
        target=name, ok=True,
        extra={"sha256": sha, "files_removed": removed},
    )
    return RedirectResponse(
        url=f"/transcripts?view=archived&did=delete&name={name}",
        status_code=303,
    )
