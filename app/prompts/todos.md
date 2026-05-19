---
key: todos
description: Action items raised in the conversation, with owner + anchor.
returns: list[dict]
---
Extract concrete action items / todos raised in the transcript.
Things someone said they (or another person) WILL DO. Not just opinions.

Each item has:
- "who": speaker label (e.g. "spk_0") OR a name if explicitly stated. Use "?" if unclear.
- "what": one short sentence describing the action (≤20 words).
- "by_when": ISO date "YYYY-MM-DD" if a date was mentioned, else null.
- "anchor_sec": float — start_sec of the segment where the todo was raised.

Constraints:
- Respond ONLY with JSON of the shape: {"todos": [{...}, ...]}
- Each "what" written in: {language_name}
- Return empty list if no clear action items.

Transcript:
{transcript_text}
