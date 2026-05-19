---
key: named_entities
description: People / places / products / dates mentioned in the transcript.
returns: dict
---
Extract named entities from the transcript, grouped by type.

- "people": personal names (full names if given, first-name otherwise).
- "places": cities, countries, venues, named regions.
- "products": product/brand names, software, hardware, services.
- "dates": calendar references that resolve to specific dates (skip vague "next week").

Constraints:
- Respond ONLY with JSON of the shape:
  {"named_entities": {"people":[], "places":[], "products":[], "dates":[]}}
- All four keys must be present (empty list is fine).
- Names in their NATIVE script (Ukrainian / Russian / English / etc.) — do not transliterate.
- Deduplicate within each group. Capitalise as in the transcript.

Transcript:
{transcript_text}
