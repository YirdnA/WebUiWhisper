from __future__ import annotations

import contextlib
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from .config import Settings, get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ip TEXT,
    user TEXT,
    action TEXT NOT NULL,
    target TEXT,
    ok INTEGER NOT NULL DEFAULT 1,
    extra TEXT
);
CREATE INDEX IF NOT EXISTS audit_log_ts_idx ON audit_log(ts);
CREATE INDEX IF NOT EXISTS audit_log_user_idx ON audit_log(user);

CREATE TABLE IF NOT EXISTS sessions (
    sid TEXT PRIMARY KEY,
    user TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    ip TEXT
);

-- Reserved for Tier C
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TEXT NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
"""


async def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    settings.state_db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(settings.state_db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@contextlib.asynccontextmanager
async def get_db(settings: Settings | None = None) -> AsyncIterator[aiosqlite.Connection]:
    settings = settings or get_settings()
    async with aiosqlite.connect(settings.state_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
