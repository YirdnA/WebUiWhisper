"""Cleanup-policy editor. Reads + writes /var/lib/webuiwhisper/policy.json
(shared volume with whisper-watcher). The watcher re-reads it at each sweep
iteration; no container restart needed."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..audit import record as audit_record
from ..config import Settings
from ..deps import current_user, require_csrf, settings_dep
from ..rate_limit import limiter

router = APIRouter(prefix="/policy", tags=["policy"])

log = logging.getLogger("webuiwhisper.policy")

# Fields, casters, and inclusive bounds. Must stay in sync with the watcher's
# _POLICY_KEYS in /opt/whisper/watcher/watcher.py.
FIELDS: dict[str, dict[str, Any]] = {
    "backup_retention_days": {"caster": int,   "lo": 1,    "hi": 365,
                              "help": "Days to keep source audio in /backup/ before sweep deletes it.",
                              "default": 6},
    "max_cpu":               {"caster": float, "lo": 0.1,  "hi": 32.0,
                              "help": "Watcher pauses transcription dispatch when the host's 1-min "
                                      "load exceeds this.",
                              "default": 0.75},
    "min_ram_gb":            {"caster": float, "lo": 0.5,  "hi": 1024.0,
                              "help": "Minimum free RAM (GiB) required to dispatch a transcription.",
                              "default": 4.0},
}


def _templates(request: Request):
    return request.app.state.templates


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "-"
    return request.client.host


def _read_policy(policy_path: Path) -> dict:
    """Best-effort read of the current policy file. Missing/invalid → {}."""
    try:
        with open(policy_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _validate(form: dict) -> tuple[dict, dict[str, str]]:
    """Return (clean_overrides, field_errors). Empty values omit the key
    (= revert to watcher default). Range or type errors populate
    `field_errors[name] = message`."""
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, spec in FIELDS.items():
        raw = str(form.get(name, "")).strip()
        if not raw:
            continue
        try:
            value = spec["caster"](raw)
        except (TypeError, ValueError):
            errors[name] = f"must be a {spec['caster'].__name__}"
            continue
        if not (spec["lo"] <= value <= spec["hi"]):
            errors[name] = f"out of range ({spec['lo']}–{spec['hi']})"
            continue
        clean[name] = value
    return clean, errors


def _write_policy(policy_path: Path, payload: dict) -> None:
    """Atomic write: tmp file in same dir, fsync, rename."""
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = policy_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        try:
            import os as _os
            _os.fsync(fh.fileno())
        except OSError:
            pass
    tmp.replace(policy_path)


def _context(settings: Settings, *, errors: dict[str, str] | None = None,
             form: dict | None = None) -> dict:
    current = _read_policy(settings.policy_path)
    fields = []
    for name, spec in FIELDS.items():
        # On error redisplay user input; else current persisted value.
        if form is not None and name in form:
            shown = form[name]
        else:
            shown = current.get(name, "")
        fields.append({
            "name": name,
            "value": shown,
            "default": spec["default"],
            "lo": spec["lo"],
            "hi": spec["hi"],
            "help": spec["help"],
            "active": name in current,   # currently sourced from the policy file
            "error": (errors or {}).get(name),
        })
    return {
        "page": "policy",
        "fields": fields,
        "policy_path": str(settings.policy_path),
        "any_errors": bool(errors),
        "current": current,
    }


@router.get("", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def policy_view(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
):
    ctx = _context(settings)
    ctx["user"] = user
    return _templates(request).TemplateResponse(request, "policy/edit.html", ctx)


@router.post("", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def policy_submit(
    request: Request,
    user: str = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    raw = await request.form()
    form = {k: str(v) for k, v in raw.items() if not k.startswith("ww_")}

    clean, errors = _validate(form)
    ip = _client_ip(request)

    if errors:
        await audit_record(
            "policy-update-rejected", user=user, ip=ip, target=str(settings.policy_path),
            ok=False, extra={"errors": errors},
        )
        ctx = _context(settings, errors=errors, form=form)
        ctx["user"] = user
        return _templates(request).TemplateResponse(
            request, "policy/edit.html", ctx, status_code=400,
        )

    before = _read_policy(settings.policy_path)
    try:
        _write_policy(settings.policy_path, clean)
    except OSError as exc:
        log.exception("policy write failed: %s", exc)
        await audit_record(
            "policy-update-fail", user=user, ip=ip, target=str(settings.policy_path),
            ok=False, extra={"err": str(exc)},
        )
        raise HTTPException(status_code=500, detail="could not write policy file") from exc

    await audit_record(
        "policy-update", user=user, ip=ip, target=str(settings.policy_path), ok=True,
        extra={"before": before, "after": clean},
    )
    return RedirectResponse(url="/policy?saved=1", status_code=303)
