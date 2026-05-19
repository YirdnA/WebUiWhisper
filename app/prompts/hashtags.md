---
key: hashtags
description: 3-8 short tags suitable for topic filtering across transcripts.
returns: list[str]
---
Suggest 3-8 hashtags that capture the main topics. These will be used
to filter and group transcripts across the library.

Constraints:
- Respond ONLY with JSON of the shape: {"hashtags": ["#...", "#..."]}
- Each tag starts with "#" and is lowercase.
- Tags are SHORT — single words or short compound words. No spaces inside a tag.
- Use the source language ({language_name}). Russian/Ukrainian tags use Cyrillic.
- Do not include speaker labels or filler words. Avoid duplicates.

Transcript:
{transcript_text}
