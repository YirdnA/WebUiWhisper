"""Thin async wrapper around the upstream whisper HTTP API."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("webuiwhisper.whisper_client")


class WhisperClientError(RuntimeError):
    pass


class WhisperClient:
    def __init__(self, settings: Settings):
        self._base = settings.whisper_api_url.rstrip("/")
        # health/models probes are quick; transcription requests can run for
        # hours on CPU — match the watcher's 8-hour ceiling.
        self._short_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._long_client = httpx.AsyncClient(timeout=httpx.Timeout(60 * 60 * 8))

    async def aclose(self) -> None:
        await self._short_client.aclose()
        await self._long_client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            r = await self._short_client.get(f"{self._base}/health")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            log.warning("upstream health failed: %s", exc)
            raise WhisperClientError(str(exc)) from exc

    async def models(self) -> list[str]:
        try:
            r = await self._short_client.get(f"{self._base}/models")
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except httpx.HTTPError as exc:
            raise WhisperClientError(str(exc)) from exc

    async def transcribe_file(
        self,
        path: str,
        model: str,
        num_speakers: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"path": path, "model": model}
        if num_speakers is not None:
            body["num_speakers"] = num_speakers
        try:
            r = await self._long_client.post(f"{self._base}/transcribe-file", json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            log.error("transcribe-file failed: %s", exc)
            raise WhisperClientError(str(exc)) from exc

    async def rediarize(
        self,
        basename: str,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"basename": basename}
        if num_speakers is not None:
            body["num_speakers"] = num_speakers
        if min_speakers is not None:
            body["min_speakers"] = min_speakers
        if max_speakers is not None:
            body["max_speakers"] = max_speakers
        try:
            r = await self._long_client.post(f"{self._base}/rediarize", json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            log.error("rediarize failed: %s", exc)
            raise WhisperClientError(str(exc)) from exc
