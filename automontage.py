"""🪄 Automatinis montažas: kirpimai pagal kalbą, matomą veiksmą ir muzikos ritmą.

Kalbantis klipas – kerpama prie frazių ribų (pradžia prieš pirmą žodį, pabaiga po paskutinio); ilgos pauzės
viduje sutrumpinamos įprastu tylos kirpimu (natūralus ritmas paliekamas – trumpos pauzės nekerpamos).
Klipas be kalbos – paliekama ryškiausio veiksmo atkarpa, o kirpimas daromas judesio metu; jei parinkta muzika,
atkarpos trukmė derinama prie muzikos takto. Vartotojo klipų eilė nekeičiama.
"""
import subprocess

import numpy as np

import video_editor

SPEECH_PAD_IN = 0.15    # s prieš pirmą žodį
SPEECH_PAD_OUT = 0.3    # s po paskutinio žodžio (vieta J perėjimui ir natūraliam atokvėpiui)
ACTION_LEN = 3.5        # s – klipo be kalbos atkarpa
ACTION_MIN_CLIP = 4.5   # trumpesni klipai be kalbos nekerpami (tik derinami prie takto)
JCUT = 0.25             # s – kito kadro garsas prasideda anksčiau už vaizdą


def motion_curve(path, fps=10):
    """Matomo judesio stiprumas kas 1/fps s (gretimų kadrų skirtumas, sumažinta raiška)."""
    w, h = 64, 36
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"fps={fps},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    if n < 3:
        return np.zeros(0)
    f = np.frombuffer(raw[: n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    return np.convolve(d, np.ones(3) / 3, mode="same")


def music_beat(path, sr=11025):
    """Muzikos takto trukmė (s) arba None. Garso energijos pokyčiai + autokoreliacija (70–170 BPM)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-t", "40", "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 256
    n = len(x) // hop
    if n < 200:
        return None
    e = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    onset = np.maximum(0, np.diff(np.log(e + 1e-4)))
    onset -= onset.mean()
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    fr = sr / hop  # langų per sekundę
    lo, hi = int(fr * 60 / 170), int(fr * 60 / 70)
    if hi >= len(ac) or ac[0] <= 0:
        return None
    lag = lo + int(np.argmax(ac[lo:hi]))
    if ac[lag] < 0.1 * ac[0]:
        return None
    return lag / fr


def speech_bounds(path):
    """(pirmo žodžio pradžia, paskutinio pabaiga) s arba None."""
    an = video_editor.analyze_audio(path)
    if an is None or not an["speech"]:
        return None
    v = np.where(an["levels"] > an["threshold"])[0]
    if not len(v):
        return None
    return float(v[0] * video_editor.FRAME), float((v[-1] + 1) * video_editor.FRAME)


def action_window(curve, fps, length, dur, exact=False):
    """Ryškiausio veiksmo atkarpa (a, b): didžiausias vidutinis judesys; pabaiga – judesio piko metu
    (exact – trukmė nekeičiama, pvz. kai ji suderinta su muzikos taktu)."""
    n = int(round(length * fps))
    if len(curve) <= n or n < 2:
        return 0.0, dur
    sums = np.convolve(curve, np.ones(n), mode="valid")
    a = int(np.argmax(sums))
    b = a + n
    if exact:
        return a / fps, min(dur, b / fps)
    # kirpimas judesio metu: pabaiga paslenkama į judesio piką paskutinėje atkarpos dalyje
    tail = max(a + n // 2, b - int(0.6 * fps))
    peak = tail + int(np.argmax(curve[tail:b])) if b > tail else b
    b = min(len(curve), max(peak + 1, a + int(n * 0.6)))
    return a / fps, min(dur, b / fps)


def plan(clips, music_path=None):
    """Montažo planas: [{"id", "trim": [a, b], "why"}] (eilė nekeičiama). Nuotraukos – nekeičiamos."""
    beat = music_beat(music_path) if music_path else None
    out = []
    for c in clips:
        if c.get("image") or not c.get("path"):
            continue
        dur = float(c["duration"])
        if c.get("audio") == "speech":
            sb = speech_bounds(c["path"])
            if sb:
                a = max(0.0, sb[0] - SPEECH_PAD_IN)
                b = min(dur, sb[1] + SPEECH_PAD_OUT)
                if b - a >= 0.5:
                    out.append({"id": c["id"], "trim": [round(a, 2), round(b, 2)],
                                "why": "kalba – kirpta prie frazių ribų, ilgos pauzės sutrumpinamos"})
                    continue
        length = ACTION_LEN
        if beat:  # trukmė – sveikas taktų skaičius
            length = max(2, round(ACTION_LEN / beat)) * beat
        if dur > max(ACTION_MIN_CLIP, length + 0.5):
            fps = 10
            a, b = action_window(motion_curve(c["path"], fps), fps, length, dur, exact=bool(beat))
            out.append({"id": c["id"], "trim": [round(a, 2), round(b, 2)],
                        "why": "be kalbos – ryškiausias veiksmas, kirpta judesio metu"
                        + (" pagal muzikos taktą" if beat else "")})
        elif beat and dur >= 2 * beat:
            b = int(dur / beat) * beat
            out.append({"id": c["id"], "trim": [0.0, round(b, 2)], "why": "be kalbos – suderinta su muzikos taktu"})
    return out, beat
