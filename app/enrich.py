"""Local-LLM enrichment of transcripts.

Drives a host-side Ollama (default `qwen2.5:7b`) to extract structured
metadata (summary, todos, hashtags, etc.) and an embedding from a
transcript JSON. Results are written to a sidecar `{name}.enrich.json`
plus a human-readable `{name}.enrich.md` (and timecoded variant).

The canonical `{name}.json` transcript is **never** modified.

Key design points:
- Prompts live as standalone Markdown files under `app/prompts/*.md`.
  Each file has a YAML front-matter with `key`, `description`, `returns`.
  Edits to a prompt take effect on next enrich run; no restart needed.
- Patterns run sequentially. CPU-only host with no GPU; parallel runs
  would just thrash.
- Output language follows the transcript's `payload.language` (ISO
  code → human name like "Ukrainian" / "Russian" / "English").
- Ollama's `format="json"` mode is requested for deterministic parsing.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("webuiwhisper.enrich")

SIDECAR_SUFFIX = ".enrich.json"
SIDECAR_MD_SUFFIX = ".enrich.md"
SIDECAR_MD_TIMECODED_SUFFIX = ".enrich.timecoded.md"

SCHEMA_VERSION = 1

DEFAULT_PATTERN_ORDER = (
    "title", "summary_tldr", "summary", "main_ideas",
    "todos", "decisions", "open_questions", "named_entities",
    "hashtags", "chapters", "quotes", "sentiment", "follow_up_draft",
)

# Embedding is an independent pattern with its own toggle.
EMBEDDING_KEY = "embedding"

# Best-effort ISO code → readable name. Falls back to the bare code if unknown.
_LANGUAGE_NAMES = {
    "uk": "Ukrainian",
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pl": "Polish",
    "cs": "Czech",
    "nl": "Dutch",
    "pt": "Portuguese",
    "tr": "Turkish",
}


def language_name(iso_code: str) -> str:
    code = (iso_code or "").strip().lower()
    return _LANGUAGE_NAMES.get(code, code or "the same language as the transcript")


# ── prompt loading ──────────────────────────────────────────────────────────


_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_prompt_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = _FRONT_MATTER_RE.match(text)
    meta: dict[str, str] = {}
    body = text
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        body = text[m.end():]
    return {
        "key": meta.get("key") or path.stem,
        "description": meta.get("description", ""),
        "returns": meta.get("returns", "string"),
        "body": body.strip(),
    }


def _load_prompts() -> dict[str, dict[str, Any]]:
    here = Path(__file__).parent / "prompts"
    out: dict[str, dict[str, Any]] = {}
    if not here.is_dir():
        return out
    for p in sorted(here.glob("*.md")):
        meta = _parse_prompt_file(p)
        out[meta["key"]] = meta
    return out


# Load once at module-import; prompts are tiny and stable for the
# lifetime of the process. Tests can call `_reload_prompts()` if needed.
PROMPTS: dict[str, dict[str, Any]] = _load_prompts()


def _reload_prompts() -> None:
    global PROMPTS
    PROMPTS = _load_prompts()


def prompt_descriptions() -> dict[str, str]:
    """Map pattern key → one-line description (for the settings UI)."""
    return {k: v.get("description", "") for k, v in PROMPTS.items()}


# ── enabled-patterns settings ──────────────────────────────────────────────


def load_enabled_patterns(settings: Settings) -> set[str]:
    """Read the instance settings file. Returns the set of enabled pattern
    keys. Missing/invalid file → all patterns + embedding enabled."""
    default = set(DEFAULT_PATTERN_ORDER) | {EMBEDDING_KEY}
    path = getattr(settings, "enrich_settings_path", None)
    if path is None or not Path(path).is_file():
        return default
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(data, dict):
        return default
    patterns = data.get("patterns")
    if not isinstance(patterns, dict):
        return default
    out: set[str] = set()
    for key, enabled in patterns.items():
        if enabled and key in (set(DEFAULT_PATTERN_ORDER) | {EMBEDDING_KEY}):
            out.add(key)
    return out


def save_enabled_patterns(enabled: set[str], settings: Settings) -> None:
    """Atomic write of the toggles file. Caller owns audit logging."""
    path = Path(settings.enrich_settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": 1,
        "patterns": {
            key: (key in enabled)
            for key in (*DEFAULT_PATTERN_ORDER, EMBEDDING_KEY)
        },
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    import os
    os.replace(tmp, path)


# ── Ollama client ──────────────────────────────────────────────────────────


class OllamaError(RuntimeError):
    """Raised on any Ollama failure (connect, HTTP, decode)."""


class OllamaClient:
    """Thin async wrapper around Ollama's HTTP API.

    Only the two endpoints we use are exposed:
    - `chat(messages, format="json")` for prompt-driven extraction
    - `embeddings(text)` for nomic-embed-text vectors
    """

    def __init__(self, base_url: str, model: str,
                 timeout_sec: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(timeout_sec, connect=10.0)

    async def chat(self, prompt: str, *, json_mode: bool = True) -> str:
        """Single-turn chat completion. Returns the model's response text."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if json_mode:
            body["format"] = "json"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise OllamaError(f"ollama unreachable: {exc}") from exc
        if r.status_code != 200:
            raise OllamaError(f"ollama HTTP {r.status_code}: {r.text[:200]}")
        try:
            payload = r.json()
        except ValueError as exc:
            raise OllamaError(f"ollama returned non-JSON envelope") from exc
        content = payload.get("message", {}).get("content", "")
        if not isinstance(content, str):
            raise OllamaError("ollama response missing message.content")
        return content

    async def embeddings(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
        except httpx.HTTPError as exc:
            raise OllamaError(f"ollama embeddings unreachable: {exc}") from exc
        if r.status_code != 200:
            raise OllamaError(f"ollama embeddings HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise OllamaError("ollama embeddings non-JSON response") from exc
        vec = data.get("embedding")
        if not isinstance(vec, list):
            raise OllamaError("ollama embeddings missing 'embedding'")
        return [float(x) for x in vec]


# ── transcript-text helpers ─────────────────────────────────────────────────


def _transcript_text(payload: dict) -> str:
    """Build the LLM input text from transcript segments."""
    lines: list[str] = []
    for seg in payload.get("segments") or []:
        ts = seg.get("start_time") or ""
        spk = seg.get("speaker") or "?"
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{ts}] {spk}: {text}")
    return "\n".join(lines)


def _transcript_sha256(payload: dict) -> str:
    """SHA256 over the segments-only canonical form. Used to detect when an
    edit has invalidated a prior enrichment."""
    canonical = json.dumps(
        payload.get("segments") or [],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── pattern orchestration ──────────────────────────────────────────────────


def _render_prompt(key: str, payload: dict, transcript_text: str) -> str:
    """Token substitution that's safe against JSON braces in the prompt body.
    We can't use str.format() because the prompts contain literal JSON
    examples like `{"title": "..."}` which break `.format`."""
    body = PROMPTS[key]["body"]
    body = body.replace("{language_name}", language_name(payload.get("language", "")))
    body = body.replace("{transcript_text}", transcript_text)
    return body


def _parse_pattern_response(key: str, raw: str) -> Any:
    """Ollama's `format=json` returns a JSON string; parse and extract the
    pattern-specific shape per its prompt contract."""
    raw = (raw or "").strip()
    if not raw:
        return _empty_for_pattern(key)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("pattern %s: JSON decode failed; raw=%s", key, raw[:200])
        return _empty_for_pattern(key)
    if not isinstance(obj, dict):
        return _empty_for_pattern(key)
    # Prompts wrap their result under the pattern key.
    if key in obj:
        return obj[key]
    # Some models nest results differently; accept a singleton dict.
    if len(obj) == 1:
        return next(iter(obj.values()))
    return _empty_for_pattern(key)


def _empty_for_pattern(key: str) -> Any:
    """Return a plausibly-empty value for the pattern's declared `returns`
    type, so a render-time consumer never sees `None`."""
    returns = PROMPTS.get(key, {}).get("returns", "string")
    if returns == "list[str]":
        return []
    if returns == "list[dict]":
        return []
    if returns == "dict":
        if key == "named_entities":
            return {"people": [], "places": [], "products": [], "dates": []}
        if key == "sentiment":
            return {"overall": "neutral", "per_speaker": {}}
        return {}
    return ""


async def _run_pattern(
    client: OllamaClient,
    key: str,
    payload: dict,
    transcript_text: str,
) -> Any:
    """Run a single pattern. Errors are logged and converted to empty values
    so a partial failure doesn't abort the whole run."""
    if key not in PROMPTS:
        log.warning("unknown pattern key: %s", key)
        return _empty_for_pattern(key)
    prompt = _render_prompt(key, payload, transcript_text)
    try:
        raw = await client.chat(prompt, json_mode=True)
    except OllamaError as exc:
        log.warning("pattern %s ollama-fail: %s", key, exc)
        raise
    return _parse_pattern_response(key, raw)


async def enrich(
    payload: dict,
    *,
    enabled: set[str],
    model: str,
    embed_model: str,
    settings: Settings,
    source_filename: str,
) -> dict:
    """Run all enabled patterns; return the sidecar dict (not yet persisted).

    Raises OllamaError if Ollama is unreachable for the FIRST request — we
    fail fast so the user sees the connectivity problem immediately. Per-
    pattern failures after that point are tolerated and logged.
    """
    ollama_url = getattr(settings, "ollama_base_url", "http://host.docker.internal:11434")
    transcript_text = _transcript_text(payload)
    sha = _transcript_sha256(payload)

    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": source_filename,
        "transcript_sha256": sha,
        "model": model,
        "embed_model": embed_model,
        "ran_at": _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "language": payload.get("language", "?"),
        "patterns": {},
        "failures": {},
    }
    started = time.monotonic()

    text_client = OllamaClient(ollama_url, model)

    # Order: code default order; honour enable-set; embeddings last so we
    # always have the text-pattern results even if the embed model is missing.
    for key in DEFAULT_PATTERN_ORDER:
        if key not in enabled:
            continue
        try:
            out["patterns"][key] = await _run_pattern(text_client, key, payload, transcript_text)
        except OllamaError as exc:
            out["failures"][key] = str(exc)
            out["patterns"][key] = _empty_for_pattern(key)

    if EMBEDDING_KEY in enabled:
        embed_client = OllamaClient(ollama_url, embed_model)
        try:
            vec = await embed_client.embeddings(transcript_text)
            out["embedding"] = {"whole": vec}
        except OllamaError as exc:
            out["failures"][EMBEDDING_KEY] = str(exc)

    out["proc_sec"] = round(time.monotonic() - started, 2)
    return out


# ── sidecar I/O ─────────────────────────────────────────────────────────────


def sidecar_paths(name: str, settings: Settings, *, archived: bool) -> dict[str, Path]:
    from .fs import ARCHIVE_DIRNAME
    base = settings.transcripts_dir / ARCHIVE_DIRNAME if archived else settings.transcripts_dir
    return {
        "json": base / f"{name}{SIDECAR_SUFFIX}",
        "md": base / f"{name}{SIDECAR_MD_SUFFIX}",
        "md_timecoded": base / f"{name}{SIDECAR_MD_TIMECODED_SUFFIX}",
    }


def read_sidecar(name: str, settings: Settings) -> dict | None:
    """Read `{name}.enrich.json` from whichever tier holds it."""
    from .fs import find_transcript_path
    found = find_transcript_path(name, settings)
    if not found:
        return None
    _, archived = found
    paths = sidecar_paths(name, settings, archived=archived)
    if not paths["json"].is_file():
        return None
    try:
        return json.loads(paths["json"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_sidecar(name: str, sidecar: dict, settings: Settings, *, archived: bool) -> None:
    """Atomic write of the JSON sidecar."""
    import os
    paths = sidecar_paths(name, settings, archived=archived)
    paths["json"].parent.mkdir(parents=True, exist_ok=True)
    tmp = paths["json"].with_suffix(paths["json"].suffix + ".tmp")
    tmp.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, paths["json"])


def delete_sidecars(name: str, settings: Settings, *, archived: bool) -> int:
    """Remove all enrich sidecars (.enrich.json, .enrich.md, .enrich.timecoded.md).
    Returns count removed. The canonical {name}.json is never touched."""
    paths = sidecar_paths(name, settings, archived=archived)
    removed = 0
    for p in paths.values():
        try:
            p.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("delete sidecar failed %s: %s", p, exc)
    return removed
