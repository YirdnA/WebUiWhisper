# Autonomous run status — Tier D

Started: 2026-05-20

Sequence: Tier C WIP commit → D1 → D7 → D2 → D3 → D6 → D4 → D5.
Plan: `/home/chai/.claude/plans/cp-cannot-stat-env-example-fizzy-sprout.md`

## Log

- 2026-05-20 — run started; tasks created; STATUS.md initialised.
- 2026-05-20 — Tier C WIP commit: **DONE** — commit `66a92c6` "feat: complete Tier B + Tier C operator pages". 37 files, 2552 insertions. 144/144 tests pass.
- 2026-05-20 — **push to main blocked** by the auto-mode classifier ("did not explicitly authorize pushing to main"). Continuing with local commits only; you can push all of them at once when you return:
  - `git push origin main`
- 2026-05-20 — moving on to D1 (AAC support).
- 2026-05-20 — **D1 DONE** — commit `31bd441` "feat(upload): add AAC support". 153/153 webuiwhisper tests pass. 16/16 watcher tests pass (2 new AAC cases). Watcher image rebuilt; running container restarted; `.aac` confirmed in `AUDIO_EXTS` of live container.
  - **Note:** `/opt/whisper/` is not a git repo on this host. The watcher source/test edits there are not version-controlled here. You may want to `git init` it or push the edited files to wherever you keep the canonical copy. The edited files:
    - `/opt/whisper/watcher/watcher.py` (AUDIO_EXTS, doc-string)
    - `/opt/whisper/watcher/tests/test_watcher_retry.py` (two new tests)
- 2026-05-20 — moving on to D7 (archive workflow + safe delete + inline download).
- 2026-05-20 — **D7 DONE** — commit `cb0074b`. Live (11) / Archived (0) tabs render; inline ⬇ buttons present; delete gated behind typed-confirm modal; bulk delete refuses live targets. 170/170 tests pass. Image rebuilt + container restarted.
- 2026-05-20 — moving on to D2 (enrich backend).
- 2026-05-20 — **Operator action needed for D2 runtime use:** the host's Ollama (`/bin/ollama serve`, root PID 3548455) listens on `127.0.0.1:11434` only. The webuiwhisper container can resolve `host.docker.internal` → `172.17.0.1` (the docker bridge gateway) thanks to a new `extra_hosts` entry, BUT Ollama itself does not bind to that interface, so `httpx.ConnectTimeout` results. Fix once you return:
  - Restart Ollama with `OLLAMA_HOST=0.0.0.0:11434` (or specifically `172.17.0.1:11434`). On a systemd-managed install: `sudo systemctl edit ollama` and add `Environment=OLLAMA_HOST=0.0.0.0`. The current process appears not to be under systemd — it's started directly as root.
  - D2 backend code is written and committed regardless; routes will return 502 with a clear message until Ollama is reachable.
- 2026-05-20 — webuiwhisper compose now has `/transcripts:rw` (was `:ro`) so sidecar writes succeed. The durability rule is enforced in code: only `*.display_name`, `*.enrich.*`, `*.json.v*` get written; the canonical `{name}.json` is never touched. Container rebuilt and restarted.
- 2026-05-20 — **D2 DONE** — commit `9fd6efa`. Enrich backend modules (`app/enrich.py`, `app/enrich_md.py`, `app/enrich_lock.py`), 13 prompt files at `app/prompts/`, two routes (enrich + settings_enrich), settings UI page, 15 new tests. 185/185 pass. Image rebuilt + container restarted. `/settings/enrich` reachable (200). LLM calls will start working once Ollama is rebound to 0.0.0.0 — code is ready.
- 2026-05-20 — moving on to D3 (enrich UI on the detail page).
- 2026-05-20 — **D3 DONE** — commit `b496a07`. Detail page has the enrich `<details>` panel + form + downloads, timecode toggle switch, anchor click-to-seek (chapters / todos / decisions / quotes), HTMX poll while in flight. List page has Tags column + tag= filter + clear-filter banner. 185/185 tests pass. Image rebuilt + container restarted; smoke pages 200.
- 2026-05-20 — moving on to D6 (auto-name + rename).
