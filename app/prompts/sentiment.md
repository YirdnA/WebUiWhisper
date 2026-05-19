---
key: sentiment
description: Overall + per-speaker emotional tone.
returns: dict
---
Assess emotional tone. Use a short label from:
{"neutral","positive","heated","tense","supportive","skeptical","frustrated"}

Output:
- "overall": one label from the set.
- "per_speaker": map of speaker_label → label.

Constraints:
- Respond ONLY with JSON of the shape:
  {"sentiment": {"overall": "neutral", "per_speaker": {"spk_0": "neutral"}}}
- Per-speaker entries only for speakers that actually appear in the transcript.
- If you cannot tell, use "neutral".

Transcript:
{transcript_text}
