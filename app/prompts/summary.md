---
key: summary
description: 3-5 sentence paragraph summary of the conversation.
returns: string
---
Read the transcript and produce a 3-5 sentence paragraph summary.
Cover: what was discussed, who said what (if speakers are clear),
key decisions or outcomes, and any explicit follow-ups.

Constraints:
- Respond ONLY with JSON of the shape: {"summary": "..."}
- Written in: {language_name}
- Plain prose — no bullets, no headings. Use sentences, not fragments.

Transcript:
{transcript_text}
