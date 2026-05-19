---
key: title
description: One short title (3-7 words) capturing the main subject.
returns: string
---
You will receive a transcript of a conversation or recording.
Produce a short title (3-7 words) capturing the main subject.

Constraints:
- Respond ONLY with JSON of the shape: {"title": "..."}
- Title must be written in: {language_name}
- No quotation marks inside the title. No emoji. No trailing period.
- If the transcript is empty or off-topic, return {"title": ""}.

Transcript:
{transcript_text}
