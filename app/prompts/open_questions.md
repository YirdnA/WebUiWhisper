---
key: open_questions
description: Questions raised but not answered during the conversation.
returns: list[str]
---
Extract questions that were raised in the transcript but NOT clearly
answered or resolved within it. Use cases: meeting follow-ups, research
agendas, things to ask the customer.

Constraints:
- Respond ONLY with JSON of the shape: {"open_questions": ["...", "..."]}
- Each item is a complete interrogative sentence in: {language_name}
- Up to 8 items. Empty list if everything got answered.

Transcript:
{transcript_text}
