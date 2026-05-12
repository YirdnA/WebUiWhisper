"""Initialise the WebUiWhisper SQLite state DB.

Idempotent — safe to re-run. Reads STATE_DB_PATH from the environment via
the same Settings object the app uses.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import init_db  # noqa: E402


def main() -> int:
    asyncio.run(init_db())
    print("WebUiWhisper state DB initialised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
