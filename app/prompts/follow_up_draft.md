---
key: follow_up_draft
description: Short follow-up email draft based on the conversation.
returns: string
---
Draft a short follow-up email (max 8 lines) summarising the conversation
and confirming next steps. Tone: professional, friendly, concise.

Constraints:
- Respond ONLY with JSON of the shape: {"follow_up_draft": "..."}
- Written in: {language_name}
- Plain text body only — no subject line, no signature.
- Empty string if there's no natural follow-up (e.g. casual chatter).

Transcript:
{transcript_text}
