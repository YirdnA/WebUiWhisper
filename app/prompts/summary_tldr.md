---
key: summary_tldr
description: One sentence (≤25 words) — the elevator pitch.
returns: string
---
Read the transcript and produce a single sentence (max 25 words)
capturing the gist — what was discussed and the key outcome if any.

Constraints:
- Respond ONLY with JSON of the shape: {"summary_tldr": "..."}
- Sentence must be written in: {language_name}
- Plain prose, no bullet markers, no quotation marks.

Transcript:
{transcript_text}
