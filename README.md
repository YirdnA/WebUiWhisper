# WebUiWhisper

A lightweight, dark-theme web UI for a local
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcription
service. WebUiWhisper does **no inference of its own** — it talks to an
upstream whisper HTTP API and reads/writes a shared filesystem of audio
recordings and transcripts.

Stack: FastAPI + Jinja2 + HTMX + Pico.css + SQLite. No Node toolchain, no
client bundler. Runtime image is ~80 MB.

## Features (Tier A)

- Login (basic auth at the reverse proxy; app trusts `Remote-User`).
- Transcripts list — sortable, auto-refreshing table over `*.json` files.
- Transcript detail — timecoded segments with coloured speaker chips.
- Downloads — TXT, JSON, **SRT** (generated on the fly).
- Upload audio — drops into the watched `/calls/` dir.
- Queue view — files in `/calls/` without a matching transcript yet.
- Server health card — proxies the whisper `/health` endpoint.
- Audit log viewer.

Tiers B and C add: search/filter, SSE live progress, audio player synced
with transcripts, re-diarization, model selector, inline editor, bulk
operations, log tail, disk dashboard, cleanup-policy editor, API tokens,
multi-user with roles, email + webhook notifications. See
[`CHANGELOG.md`](CHANGELOG.md) and the upstream design doc.

## Configuration

Copy `.env.example` to `.env` and edit. Key knobs:

| Variable | Purpose |
| --- | --- |
| `WHISPER_API_URL` | Upstream whisper HTTP API. Set to your real or mocked endpoint. |
| `CALLS_DIR` / `TRANSCRIPTS_DIR` / `BACKUP_DIR` | Mount points for shared dirs. |
| `STATE_DB_PATH` | SQLite file for sessions, audit, tokens (Tier C). |
| `SESSION_SECRET` | Random 32+ byte secret. Generate with `python -c 'import secrets;print(secrets.token_hex(32))'`. |
| `MAX_UPLOAD_BYTES` | Upload ceiling. Defaults to 500 MB to match the upstream. |
| `DEFAULT_MODEL` | `large-v3` or `large-v3-turbo`. |

## Development

The included `docker-compose.yml` is **dev-only**. It launches webuiwhisper
alone; point `WHISPER_API_URL` at a real or mocked endpoint:

```bash
cp .env.example .env
# edit .env: WHISPER_API_URL=http://127.0.0.1:8000   (real, on the host)
#        or  WHISPER_API_URL=http://localhost:9999    (your own mock)

docker compose up --build
curl -sI http://127.0.0.1:8001/
```

Run tests:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest pytest-asyncio
pytest
```

## Production deployment

WebUiWhisper is intended to live **alongside** an existing whisper service
container, sharing its docker network and filesystem mounts. Add a third
service to the whisper service's `docker-compose.yml`:

```yaml
  webuiwhisper:
    build: ../webuiwhisper
    container_name: webuiwhisper
    ports:
      - "127.0.0.1:8001:8001"
    env_file: ../webuiwhisper/.env
    environment:
      WHISPER_API_URL: http://whisper:8000
    volumes:
      - /opt/wf-op/calls:/calls:rw
      - /opt/wf-op/whisper:/transcripts:ro
      - /opt/wf-op/calls/6day_backup:/backup:ro
      - webuiwhisper_state:/var/lib/webuiwhisper
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    mem_limit: 256m
    cpus: "0.5"
    depends_on:
      - whisper
    restart: unless-stopped

volumes:
  webuiwhisper_state:
```

Front it with Apache (HTTPS via Let's Encrypt, basic auth at the proxy):

```bash
sudo cp scripts/whisper.macroscop.org.conf /etc/apache2/sites-available/
sudo htpasswd -c /etc/apache2/.htpasswd-whisper <username>
sudo chown root:www-data /etc/apache2/.htpasswd-whisper && sudo chmod 0640 $_
sudo a2ensite whisper.macroscop.org && sudo apache2ctl configtest
sudo systemctl reload apache2
sudo certbot --apache -d whisper.macroscop.org
```

## Security baseline

Applied to every release:

- Bind `127.0.0.1:8001` only; Apache is the sole public path.
- HTTPS only at the proxy; HTTP redirects to HTTPS.
- Strict response headers (HSTS, frame deny, content-type nosniff, referrer,
  CSP with `default-src 'self'`).
- CSRF tokens on every state-changing form.
- Session cookies: `HttpOnly`, `Secure`, `SameSite=Strict`, 1 h idle.
- Rate limiting via [`slowapi`](https://github.com/laurentS/slowapi).
- Magic-byte upload validation via `python-magic`; 500 MB cap.
- Path-traversal guard: all file inputs constrained and resolved against
  the configured base dir before any FS access.
- Audit log: append-only file plus DB row for every login + state change.
- Container: non-root user (`1000:1000`), read-only root FS, `cap_drop: ALL`,
  `no-new-privileges`, no `/var/run/docker.sock`.
- `requirements.txt` pinned; run `pip-audit` periodically.

## Upgrading vendored assets

`app/static/htmx.min.js` and `app/static/pico.min.css` are vendored so that
the CSP can stay `script-src 'self'` / `style-src 'self'`. To upgrade:

```bash
curl -L https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o app/static/htmx.min.js
curl -L https://unpkg.com/@picocss/pico@2.0.6/css/pico.min.css -o app/static/pico.min.css
```

Verify the integrity of the downloaded files before committing.

## License

MIT — see [`LICENSE`](LICENSE).
