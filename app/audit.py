"""Append-only audit log: one DB row plus one line in a daily-rotated file.

Schema is in app.db. The file is human-tail-friendly:
    2026-05-12T08:15:03Z  ip=1.2.3.4 user=alice  upload   target=foo.flac  ok=1
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Any

import aiosqlite

from .config import Settings, get_settings
from .db import get_db

log = logging.getLogger("webuiwhisper.audit")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_file(settings: Settings, ts: str, ip: str | None, user: str | None,
                 action: str, target: str | None, ok: bool, extra: dict | None) -> None:
    try:
        settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (
            f"{ts}\tip={ip or '-'}\tuser={user or '-'}\t{action}\t"
            f"target={target or '-'}\tok={'1' if ok else '0'}"
        )
        if extra:
            line += "\t" + json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
        with open(settings.audit_log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        log.warning("audit file write failed: %s", exc)


async def record(
    action: str,
    *,
    user: str | None = None,
    ip: str | None = None,
    target: str | None = None,
    ok: bool = True,
    extra: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    ts = _now_iso()
    _append_file(settings, ts, ip, user, action, target, ok, extra)
    try:
        async with get_db(settings) as db:
            await db.execute(
                "INSERT INTO audit_log (ts, ip, user, action, target, ok, extra) "
                "VALUES (?,?,?,?,?,?,?)",
                (ts, ip, user, action, target, 1 if ok else 0,
                 json.dumps(extra, ensure_ascii=False) if extra else None),
            )
            await db.commit()
    except aiosqlite.Error as exc:
        log.warning("audit db write failed: %s", exc)


async def recent(limit: int = 200, offset: int = 0,
                 settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    async with get_db(settings) as db:
        cur = await db.execute(
            "SELECT ts, ip, user, action, target, ok, extra "
            "FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
