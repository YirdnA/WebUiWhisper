"""Project-local transcript-enrich runner.

Imports app.enrich directly (single source of truth — no prompt
duplication). Operates against /opt/webuiwhisper/transcripts/ via the
app's standard `get_settings()`.

Run from repo root after `source .venv/bin/activate`:
    python .claude/skills/transcript-enrich/run.py <name> [--patterns ...] [--model ...] [--force]

(The skill directory name contains a hyphen, so we run it as a script
rather than via `python -m` — Python's relative module names don't
allow hyphens.)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make `app` importable when run as a script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(prog="transcript-enrich")
    ap.add_argument("name", help="Transcript basename, e.g. demo.wav")
    ap.add_argument("--patterns", default="",
                    help="Comma-separated subset (default: all enabled in settings)")
    ap.add_argument("--model", default="",
                    help="Override the enrich model (default: settings.enrich_model)")
    ap.add_argument("--force", action="store_true",
                    help="Re-run even if a sidecar already exists with matching sha")
    args = ap.parse_args()

    # Defer imports until argparse has handled --help cheaply.
    from app.config import get_settings
    from app import enrich as enrich_mod
    from app.enrich_md import render_enrich_md
    from app.fs import find_transcript_path, load_transcript

    settings = get_settings()
    found = find_transcript_path(args.name, settings)
    if not found:
        print(f"transcript not found: {args.name}", file=sys.stderr)
        return 2
    json_path, archived = found

    payload = load_transcript(json_path)

    valid = set(enrich_mod.DEFAULT_PATTERN_ORDER) | {enrich_mod.EMBEDDING_KEY}
    if args.patterns:
        chosen = {p.strip() for p in args.patterns.split(",") if p.strip() in valid}
    else:
        chosen = enrich_mod.load_enabled_patterns(settings)

    # Skip if a current sidecar already covers this sha + patterns.
    if not args.force:
        existing = enrich_mod.read_sidecar(args.name, settings)
        if existing:
            same_sha = existing.get("transcript_sha256") == enrich_mod._transcript_sha256(payload)
            covered = set(existing.get("patterns") or {}) >= chosen
            if same_sha and covered:
                print(f"sidecar up-to-date for {args.name}; pass --force to re-run")
                return 0

    model = args.model or settings.enrich_model

    async def _go():
        return await enrich_mod.enrich(
            payload,
            enabled=chosen,
            model=model,
            embed_model=settings.enrich_embed_model,
            settings=settings,
            source_filename=args.name,
        )

    try:
        sidecar = asyncio.run(_go())
    except enrich_mod.OllamaError as exc:
        print(f"ollama unreachable: {exc}", file=sys.stderr)
        return 3

    enrich_mod.write_sidecar(args.name, sidecar, settings, archived=archived)
    paths = enrich_mod.sidecar_paths(args.name, settings, archived=archived)
    paths["md"].write_text(render_enrich_md(sidecar, with_timecodes=False), encoding="utf-8")
    paths["md_timecoded"].write_text(render_enrich_md(sidecar, with_timecodes=True), encoding="utf-8")

    print(f"wrote {paths['json']}")
    print(f"wrote {paths['md']}")
    print(f"wrote {paths['md_timecoded']}")

    if sidecar.get("failures"):
        print("partial failure: " + ", ".join(sidecar["failures"].keys()), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
