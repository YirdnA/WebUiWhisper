---
key: decisions
description: Explicit decisions reached during the conversation.
returns: list[dict]
---
Extract explicit DECISIONS made during the transcript — moments where
someone said "we will" / "let's" / "we agreed" / "ok so we'll go with X".
Distinct from todos: a decision is a settled choice, not pending action.

Each item:
- "what": the decision (≤25 words).
- "by": speaker who articulated it (e.g. "spk_0"), or "?" if unclear.
- "anchor_sec": float — start_sec of the relevant segment.

Constraints:
- Respond ONLY with JSON of the shape: {"decisions": [{...}, ...]}
- Written in: {language_name}
- Empty list if no clear decisions.

Transcript:
{transcript_text}
