---
key: chapters
description: Time-anchored topical chapters for navigation.
returns: list[dict]
---
Segment the transcript into 3-12 topical chapters by detecting where
the subject shifts. Each chapter is a contiguous block of segments
discussing one theme.

Each chapter:
- "start_sec": float — the start_sec of the chapter's first segment.
- "title": short title (≤8 words) in {language_name}.
- "summary": one-sentence description (≤30 words) in {language_name}.

Constraints:
- Respond ONLY with JSON of the shape: {"chapters": [{...}, ...]}
- start_sec values must be strictly increasing.
- First chapter starts at the transcript's first segment.

Transcript:
{transcript_text}
