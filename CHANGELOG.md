# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — Tier A
- Repo scaffold, Dockerfile, dev `docker-compose.yml`.
- Apache reverse-proxy vhost template (`Remote-User` basic auth at the proxy).
- Transcripts list view with sortable columns and 30 s auto-refresh.
- Transcript detail view with timecoded segments and coloured speaker chips.
- TXT / JSON / SRT downloads (SRT generated on-the-fly).
- Audio upload → drop into `/calls/`; magic-byte validation; 500 MB cap.
- Queue view of files in `/calls/` without a matching transcript.
- Server health card proxied from the upstream whisper `/health`.
- Audit log (file + DB) with viewer.
- Security baseline: CSP, HSTS, frame deny, CSRF tokens, slowapi rate limit,
  path-traversal guard, non-root container with read-only root FS.

### Added — Tier B
- Transcript search + filter on the list view (filename substring, language,
  speaker-count range, date range). Server-side filter; auto-refresh URL
  preserves the active filters.
- HTTP-Range-supporting audio playback (`/audio/{name}`) so the detail page
  player can seek; resolves audio from `/backup/` first, then `/calls/`.
- Server-Sent Events progress stream (`/progress/{basename}`) that tails
  `/transcripts/whisper.log` and tags each line by phase
  (`transcribe` / `diarize` / `merge` / `done` / `error` / `info`).
- Per-upload model selector (large-v3 vs large-v3-turbo) via a `.model`
  sidecar consumed by the watcher; defaults to env when absent.
- Re-run diarisation button on the detail page → fire-and-forget POST to the
  upstream whisper service's `/rediarize` endpoint. Optional num/min/max
  speaker hints; outcome captured in the audit log (`rediarize-start`,
  `rediarize-ok`, `rediarize-fail`).
- Versioned inline transcript editor — every save copies the live JSON to a
  `{name}.json.v{N}` sidecar before writing the new content; live TXT is
  regenerated.
- Multi-select bulk delete/archive on the list view; archive moves files to
  `{transcripts_dir}/archive/` (with an `audio/` subfolder for the source).
- Smoke-test coverage for the Tier B routes:
  `tests/test_audio_range.py`, `test_progress_classify.py`,
  `test_rediarize_run.py`, `test_edit_versioning.py`, `test_bulk_ops.py`.

### Changed
- Whisper watcher (in the sibling `/opt/whisper/` repo) now reads
  `/etc/webuiwhisper/policy.json` for hot-reloadable retention / health-gate
  overrides. The (future) Tier-C cleanup-policy editor writes that file;
  watcher re-reads at each sweep iteration and before each transcription
  dispatch. Bad or missing JSON silently falls back to the env defaults.
- `download.txt` is now **generated on the fly from the JSON segments**
  rather than read from the static `{name}.txt` file the watcher wrote.
  The default format is plain prose (no timecodes); the previous
  `[HH:MM:SS.mmm - HH:MM:SS.mmm] SPK: text` format is still available at
  `download.txt-ts` (new "TXT (timecoded)" button on the detail page).

### Added — speaker toggle + filtered downloads
- Speaker toggle bar on the transcript detail view. One chip per unique
  speaker in the transcript; click to hide that speaker's segments,
  click again to show. "Show all" button resets. State persists per
  transcript via `localStorage` under `webui:hidden-speakers:{name}`.
- All four download buttons (TXT, TXT-timecoded, JSON, SRT) honour the
  active toggle set. Internally the JS appends `?hide=A,B,…` to each
  link's href whenever the set changes, with a small `(filtered)`
  indicator next to the button.
- New `?hide=spkA,spkB` query parameter on `/transcripts/{name}/download.{fmt}`
  for all four formats. Unknown / unsafe tokens are silently dropped.
  When `hide` is empty the JSON endpoint still ships the raw file (cheap
  fast-path); otherwise downloads are streamed from a filtered payload.
- Plain-text TXT renderer (`app/txt.py`). Speaker headers only at speaker
  change; suppressed entirely when there's ≤1 unique speaker in the
  transcript (so a typical no-diarisation recording reads as clean prose).
- Pretty title on the detail page: `nanotalks_2026-05-12_19-40-56.flac`
  is rendered as `nanotalks (2026-05-12 19:40:56)`. Original filename
  preserved as the `<h2 title="...">` tooltip and used for all URLs and
  downloads.
- List view "Name" column shows just the room stem (e.g. `nanotalks`); full
  filename in the row's `title` tooltip and link target.

### Added — Tier C (operator pages)
- `/logs` — live SSE tail of `whisper.log` and `watcher.log` with two
  tabs and terminal-style colouring by phase (transcribe / diarize /
  merge / done / error / info). Auto-scroll-to-bottom unless the user
  scrolled up; auto-pause when the tab is hidden.
- `/disk` — read-only dashboard: sizes + file counts of `/calls/`,
  `/calls/6day_backup/`, `/calls/failed/`, `/transcripts/`; per-day
  transcript histogram for the last 30 days as inline SVG (no JS chart
  library, no CDN).
- `/policy` — small form to edit the cleanup-policy file
  (`backup_retention_days`, `max_cpu`, `min_ram_gb`). Atomic write,
  audit-logged, hot-reloaded by the watcher at its next sweep iteration.
  Blank field reverts that key to the env default.

### Changed — BREAKING-ish
- Cleanup-policy file moved from `/etc/webuiwhisper/policy.json` to
  `/var/lib/webuiwhisper/policy.json` (on the existing `webuiwhisper_state`
  named volume). The watcher's `/etc/webuiwhisper` bind mount is removed.
  Any hand-edited config there (none in practice) must be re-saved through
  the new `/policy` page.

### Changed — Queue page
- `/queue` now renders three sections: **In flight** (the currently-running
  transcription, detected from the tail of `watcher.log`), **Pending**
  (everything else queued), and **Failed** (dead-letter dir surfaced from
  `/calls/failed/`). Each row is one line tall with a status chip, human-
  readable size, relative "added/last fail" time, and a click-through to
  the live log page.

### Added — Queue actions
- Per-row **Retry** (move back to `/calls/`) and **Discard** (delete
  file + sidecar) buttons on Failed entries. CSRF-guarded; each writes a
  `queue-retry` / `queue-discard` audit row. Discard prompts for
  confirmation client-side.

### Added — Jinja `rel_ts` filter
- `{{ epoch | rel_ts }}` → "5 s ago" / "12 min ago" / "3 h ago" /
  "yesterday" / "N d ago" / `YYYY-MM-DD`. Used on the Queue page; available
  for any future template.
