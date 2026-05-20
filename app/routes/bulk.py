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
from ..fs import ARCHIVE_DIRNAME, find_transcript_path
from ..rate_limit import limiter

router = APIRouter(prefix="/transcripts", tags=["bulk"])

log = logging.getLogger("webuiwhisper.bulk")

_NAME_RE = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9_.\-, ()]{1,210}$")
_ARCHIVE_DIRNAME = ARCHIVE_DIRNAME
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
    """Hard delete — only allowed when the transcript is in `archive/`.

    Safety: callers must have already verified that `{name}` resolves to
    an archived file (via `find_transcript_path`). This function trusts
    that and removes from the archive dir + audio backup.
    """
    archive_dir = settings.transcripts_dir / _ARCHIVE_DIRNAME
    backup_dir = settings.backup_dir

    removed_t = 0
    # Use _related_paths against the archive dir.
    for p in _related_paths(archive_dir, name):
        if _within(p, archive_dir):
            try:
                p.unlink()
                removed_t += 1
            except OSError as exc:
                log.warning("delete failed %s: %s", p, exc)

    # Audio backup may live under archive/audio/ (legacy path used by the
    # original archive action) — clean that up too. Backup itself is owned
    # by the watcher's 6-day retention; we only touch the archived copy.
    removed_b = 0
    archive_audio = archive_dir / "audio" / name
    if archive_audio.is_file() and _within(archive_audio, archive_dir):
        try:
            archive_audio.unlink()
            removed_b = 1
        except OSError as exc:
            log.warning("archive audio delete failed %s: %s", archive_audio, exc)

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

    # Gate bulk delete: every target must already be archived. We refuse
    # the entire batch (don't silently drop unarchived names) so the
    # operator sees a clear failure and re-checks intent.
    if action == "delete":
        live_targets = []
        missing = []
        for n in safe_names:
            found = find_transcript_path(n, settings)
            if not found:
                missing.append(n)
                continue
            _, archived = found
            if not archived:
                live_targets.append(n)
        if live_targets or missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "bulk delete refused: "
                    f"{len(live_targets)} live target(s) must be archived first, "
                    f"{len(missing)} not found. "
                    "Archive them from the Live tab, then retry delete on the "
                    "Archived tab."
                ),
            )

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

    # Redirect back to whichever view the bulk action came from. Archive
    # action goes to Archived tab so the user sees where the items landed;
    # delete stays on Archived tab so the user sees the resulting list.
    view = "archived" if action in ("archive", "delete") else "live"
    return RedirectResponse(
        url=f"/transcripts?view={view}&bulk_done={action}&n={len(safe_names)}",
        status_code=303,
    )
