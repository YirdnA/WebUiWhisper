"""Speaker -> stable colour-class mapping (used by templates)."""
from __future__ import annotations

import hashlib

_PALETTE_SIZE = 8


def speaker_class(speaker: str | None) -> str:
    if not speaker or speaker == "?":
        return "spk-unknown"
    h = hashlib.sha1(speaker.encode("utf-8")).digest()
    return f"spk-{h[0] % _PALETTE_SIZE}"


def speaker_label(speaker: str | None) -> str:
    if not speaker or speaker == "?":
        return "?"
    return speaker
