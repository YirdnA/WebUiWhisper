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
