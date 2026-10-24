#!/usr/bin/env python3
"""Burn modern TikTok/Reels-style animated subtitles into a video.

Style: Montserrat Black, UPPERCASE, white text with black outline and soft
shadow, the word being spoken highlighted yellow, pop-in / fade-out per phrase.

Usage:
  python3 make_subtitles.py INPUT_VIDEO SUBS.json OUTPUT.mp4 --font Montserrat_900Black.ttf

SUBS.json is a list of phrases with their on-screen window in seconds:
  [{"text": "Kiekvienoje sunkioje situacijoje", "start": 0.0, "end": 2.4}, ...]

Word highlight timing is estimated from syllable counts, spread over the
speech found (via ffmpeg silencedetect) inside each phrase window.
"""
import argparse, json, os, re, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

YELLOW = (255, 214, 10)
WHITE = (255, 255, 255)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out); s = j["streams"][0]
    w, h = s["width"], s["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in s.get("side_data_list", []) if "rotation" in d), 0)
    if rot in (90, 270): w, h = h, w
    num, den = s["r_frame_rate"].split("/")
    return w, h, round(int(num) / int(den)), float(j["format"]["duration"])


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return bool(out.strip())


def speech_segments(path, dur):
    if not has_audio(path): return [(0.0, dur)]
    err = subprocess.run(["ffmpeg", "-i", path, "-map", "0:a:0", "-af", "silencedetect=n=-50dB:d=0.3",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    segs, t = [], 0.0
    for i, s in enumerate(starts):
        if s > t: segs.append((t, s))
        t = ends[i] if i < len(ends) else dur
    if t < dur: segs.append((t, dur))
    return segs or [(0.0, dur)]


def syllables(w):
    return max(1, len(re.findall(r"[aeiouyąęėįųū]+", w.lower())))


def word_times(words, a, b, speech):
    segs = [(max(a, s), min(b, e)) for s, e in speech if min(b, e) > max(a, s)] or [(a, b)]
    total = sum(e - s for s, e in segs)
    def at(frac):
        x = frac * total
        for s, e in segs:
            if x <= e - s: return s + x
            x -= e - s
        return segs[-1][1]
    n = sum(syllables(w) for w in words); c = 0; out = []
    for w in words:
        out.append(at(c / n)); c += syllables(w)
    return out


def ease(t):
    t = min(max(t, 0), 1); return 1 - (1 - t) ** 3


def render(args):
    W, H, fps, dur = probe(args.input)
    phrases = json.load(open(args.subs, encoding="utf-8"))
    speech = speech_segments(args.input, dur)
    fsize = round(W * 0.078); font = ImageFont.truetype(args.font, fsize)
    stroke = max(3, round(fsize / 12)); lh = round(fsize * 1.24); cy = round(H * args.ypos)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    items = []
    for p in phrases:
        words = p["text"].upper().split()
        rows = [[]]
        for i in range(len(words)):
            trial = " ".join(words[j] for j in rows[-1] + [i])
            if rows[-1] and measure.textlength(trial, font=font) > W * 0.87: rows.append([])
            rows[-1].append(i)
        items.append((words, word_times(words, p["start"], p["end"], speech), rows, p["start"], p["end"]))

    tmp = tempfile.mkdtemp(prefix="subs_")
    for fi in range(int(dur * fps)):
        t = fi / fps; im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for words, tw, rows, a, b in items:
            if not (a <= t < b): continue
            pop = ease((t - a) / 0.18); fade = min(1, (b - t) / 0.12)
            cur = max([i for i in range(len(words)) if tw[i] <= t] or [0])
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
            y0 = cy - (len(rows) - 1) * lh / 2
            for r, row in enumerate(rows):
                txt = " ".join(words[i] for i in row)
                x = (W - d.textlength(txt, font=font)) / 2; y = y0 + r * lh
                for i in row:
                    alpha = 255 if tw[i] <= t else 140
                    col = YELLOW if i == cur else WHITE
                    d.text((x, y), words[i], font=font, fill=col + (alpha,), stroke_width=stroke,
                           stroke_fill=(0, 0, 0, int(alpha * 0.9)), anchor="ls")
                    x += d.textlength(words[i] + " ", font=font)
            shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            shadow.putalpha(lay.split()[3].filter(ImageFilter.GaussianBlur(fsize / 6)).point(lambda v: int(v * 0.55)))
            lay = Image.alpha_composite(shadow.transform((W, H), Image.AFFINE, (1, 0, 0, 0, 1, -6)), lay)
            s = 0.82 + 0.18 * pop
            if s < 0.999:
                sw, sh = int(W * s), int(H * s); scaled = lay.resize((sw, sh), Image.BILINEAR)
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); lay.paste(scaled, ((W - sw) // 2, int(cy - cy * s)))
            k = pop * fade
            if k < 1: lay.putalpha(lay.split()[3].point(lambda v: int(v * k)))
            im = Image.alpha_composite(im, lay)
        im.save(os.path.join(tmp, f"{fi:05d}.png"), compress_level=1)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", args.input, "-framerate", str(fps),
           "-i", os.path.join(tmp, "%05d.png"), "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass[v]",
           "-map", "[v]", "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if has_audio(args.input):
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        if not args.no_loudnorm: cmd += ["-af", "loudnorm=I=-16:TP=-1.5"]
    cmd += ["-movflags", "+faststart", "-t", str(dur), args.output]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("subs"); ap.add_argument("output")
    ap.add_argument("--font", required=True, help="Path to Montserrat_900Black.ttf")
    ap.add_argument("--ypos", type=float, default=0.67, help="Vertical centre of captions (0-1 of height)")
    ap.add_argument("--no-loudnorm", action="store_true", help="Keep original audio level")
    render(ap.parse_args())
