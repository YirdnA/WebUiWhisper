---
name: transcript-enrich
description: Enrich a webuiwhisper transcript with summary / todos / hashtags / chapters / etc. using the host's local Ollama (qwen2.5:7b + nomic-embed-text). Writes {name}.enrich.json plus {name}.enrich.md sidecars alongside the canonical transcript. Project-local skill: only operates on this app's transcripts under /opt/webuiwhisper/transcripts/.
---

# transcript-enrich

This skill enriches a transcript already produced by the whisper service.
It is **project-local** to this repo — it only operates on the transcript
JSONs that live under `/opt/webuiwhisper/transcripts/` (or the `archive/`
subdir for archived items). It imports `app.enrich` directly so prompts
and orchestration stay in lockstep with what the HTTP route does.

## Requirements
- Host's Ollama running and reachable at `http://127.0.0.1:11434` (this is
  the **host** view; the FastAPI container uses `host.docker.internal`).
- Models pulled: `qwen2.5:7b` (default) and `nomic-embed-text`.
- Python 3.13 venv at `/opt/webuiwhisper/.venv` with the app's deps installed.

## Invocation contract
```
# Activate the app venv first so app.enrich + httpx are importable.
cd /opt/webuiwhisper
source .venv/bin/activate

# Enrich one transcript (full pattern set, default model).
python .claude/skills/transcript-enrich/run.py nanotalks_2026-05-12_19-40-56.flac

# Trim to specific patterns.
python .claude/skills/transcript-enrich/run.py demo.wav --patterns title,summary,hashtags

# Force a re-run even if the existing sidecar's transcript_sha256 matches.
python .claude/skills/transcript-enrich/run.py demo.wav --force

# Use a different model.
python .claude/skills/transcript-enrich/run.py demo.wav --model qwen2.5:3b
```

The argument is the audio basename (e.g. `foo.wav`) — the same name shown
in URLs and on disk. The skill resolves it against the live tier first,
then the archive subdir.

## Exit codes
- 0 — success
- 2 — transcript not found
- 3 — Ollama unreachable (connect failure on first call)
- 4 — partial failure (some patterns errored; sidecar still written with
  `failures: {...}` recorded)

## Outputs
Writes three sidecars next to the canonical JSON:
- `{name}.enrich.json` — structured patterns + provenance
- `{name}.enrich.md` — prose-mode markdown report
- `{name}.enrich.timecoded.md` — with `[HH:MM:SS]` markers

The canonical `{name}.json` is **never** modified.

## Why it exists when the HTTP route already does this
- Bulk runs from a Bash for-loop without HTTP/CSRF.
- Test-fixture regeneration after a prompt edit.
- Coding-session diagnostics while iterating on `app/enrich.py` —
  invoke the skill outside the docker container.
