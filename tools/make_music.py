"""Sugeneruoja Reels studijos foninės muzikos biblioteką (music/*.mp3).

Visi kūriniai sintezuojami čia pat (numpy), todėl jokių autorių teisių apribojimų nėra.
Kiekvienas kūrinys – tikslus taktų skaičius, o aidas (reverb) pritaikomas ciklinei konvoliucijai,
todėl kūrinys kartojamas be jokios sandūros.

  python3 tools/make_music.py
"""
import os
import subprocess

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "music")
rng = np.random.default_rng(7)

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name):
    """'A4' -> 440 Hz."""
    n, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[n] + 12 * (octave + 1) - 69) / 12)


def chord(root, kind="m", octave=3):
    iv = {"": [0, 4, 7, 11], "m": [0, 3, 7, 10], "maj": [0, 4, 7, 11, 14], "m9": [0, 3, 7, 10, 14],
          "sus": [0, 5, 7, 10], "7": [0, 4, 7, 10]}[kind]
    base = hz(root + str(octave))
    return [base * 2 ** (i / 12) for i in iv]


def env(n, a=0.005, d=1.0, sustain=0.0, r=0.05):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * (sustain + (1 - sustain) * np.exp(-t / d))
    rel = int(r * SR)
    if rel and n > rel:
        e[-rel:] *= np.linspace(1, 0, rel)
    return e


def piano(f, dur, vel=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = sum((0.6 ** k) * np.sin(2 * np.pi * f * (k + 1) * t * (1 + 0.0004 * k)) * np.exp(-t * (1.2 + k * 0.9))
            for k in range(6))
    return vel * x * env(n, 0.003, 9, r=0.08)


def rhodes(f, dur, vel=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    mod = 1.4 * np.exp(-t * 6) * np.sin(2 * np.pi * f * 7 * t)  # „varpelio“ ataka
    x = np.sin(2 * np.pi * f * t + mod) + 0.15 * np.sin(2 * np.pi * f * 2 * t)
    return vel * x * env(n, 0.004, 1.8, 0.15, 0.15)


def pad(freqs, dur, vel=0.25, bright=6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.004, 0, 0.0045):
            for k in range(1, bright + 1):
                x += np.sin(2 * np.pi * f * (1 + det) * k * t + rng.uniform(0, 6.28)) / (k ** 1.6)
    x /= len(freqs) * 3
    a = min(1.2, dur / 3)
    e = np.minimum(1, t / a) * np.minimum(1, (dur - t) / a)
    return vel * x * e


def bell(f, dur, vel=0.3):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t + 2.0 * np.exp(-t * 3) * np.sin(2 * np.pi * f * 3.5 * t))
    return vel * x * env(n, 0.002, 1.2, r=0.1)


def pluck(f, dur, vel=0.4):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * k * t) / k * np.exp(-t * (8 + 6 * k)) for k in range(1, 7))
    return vel * x * env(n, 0.002, 0.5, r=0.03)


def bass(f, dur, vel=0.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t) + 0.08 * np.sin(2 * np.pi * f * 3 * t)
    return vel * np.tanh(1.4 * x) * env(n, 0.006, 0.9, 0.4, 0.06)


def kick(vel=0.9):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t * 32)
    return vel * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8)


def hat(vel=0.15, open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    x = rng.standard_normal(n)
    x = x - np.convolve(x, np.ones(4) / 4, "same")  # tik aukšti dažniai
    x = np.convolve(x, np.ones(2) / 2, "same")  # be šiurkščiausių
    return 0.5 * vel * x * np.exp(-np.arange(n) / SR * (22 if open_ else 80))


def clap(vel=0.35):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    x = x - np.convolve(x, np.ones(8) / 8, "same")
    burst = sum(np.exp(-np.maximum(0, t - d) * 60) * (t >= d) for d in (0, 0.01, 0.02))
    return vel * x * burst * np.exp(-t * 18) * 0.6


def lowpass_fft(x, cutoff):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


class Track:
    def __init__(self, bpm, bars):
        self.beat = 60 / bpm
        self.n = int(round(bars * 4 * self.beat * SR))
        self.buses = {}

    def add(self, bus, sound, beat_pos, pan=0.0):
        i = int(round(beat_pos * self.beat * SR))
        buf = self.buses.setdefault(bus, np.zeros((2, self.n)))
        for ch, g in enumerate((np.sqrt(0.5 - pan / 2), np.sqrt(0.5 + pan / 2))):
            idx = (np.arange(len(sound)) + i) % self.n  # ciklas – uodega pereina į pradžią
            np.add.at(buf[ch], idx, sound * g)

    def render(self, reverb=None, master=0.9):
        """reverb: {bus: kiekis}. Ciklinė konvoliucija – kūrinys kartojasi be sandūros."""
        reverb = reverb or {}
        mix = np.zeros((2, self.n))
        for bus, buf in self.buses.items():
            mix += buf
            amt = reverb.get(bus, 0)
            if amt:
                for ch in range(2):
                    m = min(self.n, int(3.2 * SR))
                    ir = np.zeros(self.n)
                    tail = rng.standard_normal(m) * np.exp(-np.arange(m) / SR * 2.2)
                    ir[int(0.02 * SR):int(0.02 * SR) + m] = tail[:self.n - int(0.02 * SR)]
                    wet = np.fft.irfft(np.fft.rfft(buf[ch]) * np.fft.rfft(ir), self.n)
                    wet = lowpass_fft(wet, 5000)
                    mix[ch] += amt * wet / (np.abs(wet).max() + 1e-9) * np.abs(buf[ch]).max()
        mix = np.tanh(mix / (np.abs(mix).max() + 1e-9) * 1.3)
        return master * mix / np.abs(mix).max()


def save(name, stereo):
    os.makedirs(OUT, exist_ok=True)
    raw = (np.clip(stereo.T, -1, 1) * 32767).astype("<i2").tobytes()
    path = os.path.join(OUT, name + ".mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-af", "loudnorm=I=-18:TP=-1.5:LRA=9", "-ar", str(SR),
                    "-c:a", "libmp3lame", "-b:a", "160k", path], input=raw, check=True)
    print(path, f"{stereo.shape[1] / SR:.1f} s")


# ---------- Kūriniai ----------

def luxury_piano():
    """Prabangus pianinas: lėti akordai ir arpedžio, daug erdvės."""
    tr = Track(72, 16)
    prog = [("A", "m9"), ("F", "maj"), ("C", "maj"), ("G", "sus")] * 4
    for bar, (r, k) in enumerate(prog):
        notes = chord(r, k, 3)
        b = bar * 4
        tr.add("p", sum(piano(f, 4 * tr.beat, 0.22) for f in notes[:3]), b, -0.1)
        tr.add("p", piano(notes[0] / 2, 4 * tr.beat, 0.3), b)
        for j, s in enumerate([0, 1.5, 2, 3, 3.5]):
            f = notes[(j + bar) % len(notes)] * 2
            tr.add("p", piano(f, 2 * tr.beat, 0.16 + 0.04 * (j % 2)), b + s, 0.25 * ((j % 3) - 1))
        tr.add("pad", pad(notes[:3], 4 * tr.beat, 0.12, 3), b)
    return tr.render({"p": 0.55, "pad": 0.6})


def lounge():
    """Lounge: šilti elektrinio pianino akordai, minkštas ritmas ir bosas."""
    tr = Track(92, 16)
    prog = [("D", "m9"), ("G", "7"), ("C", "maj"), ("A", "m")] * 4
    for bar, (r, k) in enumerate(prog):
        notes = chord(r, k, 3)
        b = bar * 4
        for s in (0, 1.5, 2.75):
            tr.add("keys", sum(rhodes(f, 1.2 * tr.beat, 0.13) for f in notes), b + s, -0.15)
        root = notes[0] / 2
        for s, mul in ((0, 1), (1.5, 1), (2.5, 1.5), (3.5, 1)):
            tr.add("bass", bass(root * mul, 0.9 * tr.beat, 0.45), b + s)
        for s in (0, 2.5):
            tr.add("drums", kick(0.7), b + s)
        for s in (1, 3):
            tr.add("drums", clap(0.22), b + s, 0.1)
        for s in np.arange(0, 4, 0.5):
            tr.add("drums", hat(0.07 if s % 1 else 0.11), b + s + (0.06 if s % 1 else 0), 0.3)
    return tr.render({"keys": 0.45})


def cinematic():
    """Kinematografiška: platūs pasažai, žemas bosas ir lėtas pulsas."""
    tr = Track(64, 8)
    prog = [("C", "m"), ("G#", "maj"), ("D#", "maj"), ("A#", "sus")] * 2
    for bar, (r, k) in enumerate(prog):
        notes = chord(r, k, 3)
        b = bar * 4
        tr.add("pad", pad(notes[:3] + [notes[0] * 2], 5.5 * tr.beat, 0.3, 7), b - 0.6)
        tr.add("low", pad([notes[0] / 2], 5.5 * tr.beat, 0.35, 2), b - 0.6)
        for s in range(4):
            tr.add("pulse", pluck(notes[0], 0.5 * tr.beat, 0.12), b + s, 0.2)
        tr.add("drums", kick(0.6), b)
        tr.add("bell", bell(notes[2] * 4, 2 * tr.beat, 0.06), b + 2, -0.4)
    return tr.render({"pad": 0.5, "bell": 0.8, "pulse": 0.5, "drums": 0.4})


def energetic_pop():
    """Energinga: 118 BPM, tolygus būgnas, „pluck“ melodija ir bosas."""
    tr = Track(118, 16)
    prog = [("A", "m"), ("F", ""), ("C", ""), ("G", "")] * 4
    melody = [0, 2, 1, 2, 0, 3, 2, 1]
    for bar, (r, k) in enumerate(prog):
        notes = chord(r, k, 4)
        b = bar * 4
        for s in range(4):
            tr.add("drums", kick(0.95), b + s)
            tr.add("drums", hat(0.07, True), b + s + 0.5, 0.25)
        for s in (1, 3):
            tr.add("drums", clap(0.3), b + s)
        for j, s in enumerate(np.arange(0, 4, 0.5)):
            tr.add("pl", pluck(notes[melody[(j + bar) % 8]], 0.6 * tr.beat, 0.22), b + s, 0.3 * (-1) ** j)
            tr.add("bass", bass(notes[0] / 4, 0.45 * tr.beat, 0.4), b + s)
        tr.add("pad", pad(notes[:3], 4 * tr.beat, 0.1, 5), b)
    return tr.render({"pl": 0.3, "pad": 0.5})


def lofi():
    """Lo-fi: lėtas, siūbuojantis ritmas, šilti akordai ir plokštelės traškesys."""
    tr = Track(76, 16)
    prog = [("F", "maj"), ("E", "m"), ("D", "m9"), ("C", "maj")] * 4
    for bar, (r, k) in enumerate(prog):
        notes = chord(r, k, 3)
        b = bar * 4
        tr.add("keys", sum(rhodes(f, 3.6 * tr.beat, 0.1) for f in notes), b + 0.05)
        tr.add("keys", sum(rhodes(f, 1.5 * tr.beat, 0.07) for f in notes[1:]), b + 2.6)
        tr.add("bass", bass(notes[0] / 2, 1.8 * tr.beat, 0.4), b)
        tr.add("bass", bass(notes[0] / 2 * 1.5, 1.2 * tr.beat, 0.3), b + 2.5)
        tr.add("drums", kick(0.6), b)
        tr.add("drums", kick(0.45), b + 2.5)
        for s in (1, 3):
            tr.add("drums", clap(0.18), b + s + 0.03)
        for j, s in enumerate(np.arange(0, 4, 0.5)):
            tr.add("drums", hat(0.06), b + s + (0.11 if j % 2 else 0), 0.3)
    crackle = np.zeros(tr.n)
    pos = rng.integers(0, tr.n, 900)
    crackle[pos] = rng.uniform(-0.4, 0.4, len(pos))
    tr.buses["noise"] = np.stack([crackle * 0.05, np.roll(crackle, 300) * 0.05])
    mix = tr.render({"keys": 0.4})
    return np.stack([lowpass_fft(ch, 6500) for ch in mix])


def romantic():
    """Romantiška: švelnūs varpeliai virš šiltų pasažų."""
    tr = Track(80, 16)
    prog = [("E", "maj"), ("C#", "m"), ("A", "maj"), ("B", "sus")] * 4
    for bar, (r, k) in enumerate(prog):
        notes = chord(r, k, 3)
        b = bar * 4
        tr.add("pad", pad(notes[:3], 4.2 * tr.beat, 0.22, 4), b)
        tr.add("p", piano(notes[0] / 2, 4 * tr.beat, 0.25), b)
        for j, s in enumerate((0, 1, 2, 2.5, 3)):
            tr.add("bell", bell(notes[(j * 2 + bar) % len(notes)] * 4, 1.5 * tr.beat, 0.07), b + s,
                   0.4 * (-1) ** j)
    return tr.render({"pad": 0.6, "bell": 0.7, "p": 0.5})


TRACKS = {
    "prabangus_pianinas": luxury_piano,
    "lounge": lounge,
    "kinematografiska": cinematic,
    "energinga": energetic_pop,
    "lofi": lofi,
    "romantiska": romantic,
}

if __name__ == "__main__":
    import sys
    for name, fn in TRACKS.items():
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        save(name, fn())
