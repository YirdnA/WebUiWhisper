---
key: quotes
description: Memorable pull-quotes with speaker + timecode anchor.
returns: list[dict]
---
Identify up to 5 memorable pull-quotes — short, vivid lines worth
surfacing on their own.

Each quote:
- "text": the line verbatim from the transcript (≤120 chars).
- "speaker": speaker label (e.g. "spk_0").
- "anchor_sec": float — start_sec of the segment containing the line.

Constraints:
- Respond ONLY with JSON of the shape: {"quotes": [{...}, ...]}
- Quote text in its native language (do not translate).
- Empty list if nothing stands out — better empty than weak quotes.

Transcript:
{transcript_text}
