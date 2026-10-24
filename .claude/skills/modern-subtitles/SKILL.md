---
name: modern-subtitles
description: Add modern TikTok/Reels-style animated subtitles (titrai) to a video. Use whenever the user asks to add subtitles/captions/titrus to a video, or to make subtitles nicer/modern. This is the user's preferred default subtitle style.
---

# Modern subtitles (user's preferred style)

The user approved this style and wants it used by default for any video subtitles:

- Font **Montserrat Black**, text in **UPPERCASE**
- White letters with a thick black outline and a soft drop shadow, **no background box**
- The word currently being spoken is **yellow** (`#FFD60A`); spoken words are white, upcoming words dimmed
- Each phrase **pops in** (scale 0.82 → 1, ease-out ~0.18 s) and fades out
- Placed centred horizontally, about 2/3 down the frame (below the face, not over the mouth)
- Long phrases wrap to 2–3 rows
- Audio is normalised to normal loudness (`loudnorm I=-16`) unless the user says otherwise

Talk to the user in Lithuanian.

## Steps

1. **Check the audio** (`ffmpeg -af volumedetect`). If it is silent (≈ −90 dB), tell the user there is no recorded sound.
2. **Get the text.** Speech recognition models cannot be downloaded in this environment (Hugging Face is blocked), so ask the user what they say in the video unless they already gave it. Fix Lithuanian diacritics (š, ž, ė, ų, …).
3. **Find the phrases** with `ffmpeg -i VIDEO -af silencedetect=n=-50dB:d=0.3 -f null -`. Split the text into short phrases (≈ 3–5 words) and give each one a `start`/`end` window that matches the speech segments (align boundaries to pauses, using syllable counts as a guide).
4. **Get the font** (npm is reachable, Google Fonts / GitHub are not):
   ```bash
   cd "$SCRATCH" && npm pack @expo-google-fonts/montserrat --silent && tar xzf expo-google-fonts-montserrat-*.tgz
   # font: $SCRATCH/package/900Black/Montserrat_900Black.ttf
   ```
5. **Write `subs.json`**:
   ```json
   [{"text": "Kiekvienoje sunkioje situacijoje", "start": 0.0, "end": 2.4},
    {"text": "reikia daryti išvadas, analizuoti,", "start": 2.4, "end": 4.7}]
   ```
6. **Render**:
   ```bash
   python3 .claude/skills/modern-subtitles/make_subtitles.py VIDEO subs.json OUT.mp4 \
     --font "$SCRATCH/package/900Black/Montserrat_900Black.ttf"
   ```
   Options: `--ypos 0.67` (vertical position), `--no-loudnorm`.
7. **Check** a few frames (`ffmpeg -ss T -i OUT.mp4 -frames:v 1`) to confirm the captions don't cover the mouth and the diacritics render, then send the video with SendUserFile. Mention that word-highlight timing is estimated, and offer to adjust times, colour or position.
