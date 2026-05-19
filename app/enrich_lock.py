"""Global single-job lock + FIFO queue for enrichment runs.

Constraints:
- In-process state only (single-replica deployment).
- Serial execution: only one enrich job runs at a time across the whole
  app. This is the right call on a CPU-only host where whisper + ollama
  share cores.
- `queue_position(name)` returns 1-based position for a name that's
  waiting, or 0 if it's currently running, or None if not enqueued.

Use:
    async with EnrichLock.acquire("foo.flac"):
        ... do the LLM work ...
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class _State:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._waiting: list[str] = []   # names waiting, in arrival order
        self._running: str | None = None

    async def __aenter__(self) -> None:
        await self._lock.acquire()

    async def __aexit__(self, *exc) -> None:
        self._lock.release()


_state = _State()


@asynccontextmanager
async def acquire(name: str):
    """Acquire the global lock. While waiting, `name` appears in the FIFO
    queue and `queue_position(name)` reflects its position. While running,
    the name is in `_state._running`. The lock is always released on exit."""
    _state._waiting.append(name)
    try:
        # Wait for the lock — we loop because asyncio.Lock is FIFO but we
        # want to surface the queue position to callers via the helper
        # below. asyncio.Lock.acquire() is already FIFO under the hood.
        await _state._lock.acquire()
    finally:
        # Remove ourselves from the waiting list once we hold the lock
        # (or on cancellation).
        try:
            _state._waiting.remove(name)
        except ValueError:
            pass
    _state._running = name
    try:
        yield
    finally:
        _state._running = None
        _state._lock.release()


def queue_position(name: str) -> int | None:
    """0 = currently running. 1..N = waiting at that position. None = not enqueued."""
    if _state._running == name:
        return 0
    try:
        idx = _state._waiting.index(name)
    except ValueError:
        return None
    return idx + 1


def snapshot() -> dict:
    """For debugging / status pages."""
    return {
        "running": _state._running,
        "waiting": list(_state._waiting),
    }
