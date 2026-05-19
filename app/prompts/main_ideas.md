---
key: main_ideas
description: 3-7 bullet points capturing the principal topics or insights.
returns: list[str]
---
Extract the 3-7 main ideas or topics discussed in the transcript.
Each idea is a short clause (≤15 words), framed as a noun phrase or
declarative sentence — not a question.

Constraints:
- Respond ONLY with JSON of the shape: {"main_ideas": ["...", "..."]}
- Each item written in: {language_name}
- No empty strings. No duplicates. Order by importance, most important first.

Transcript:
{transcript_text}
