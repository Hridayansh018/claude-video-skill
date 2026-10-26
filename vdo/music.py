"""Background music made in code (no licence, no download), in a style that matches the story.

Styles:  calm, warm, wonder, serious        gentle storybook beds (music_classic.py)
         war        low strings ostinato, taiko drums, brass stabs, snare march, cymbal swells
         epic       cinematic strings and choir pad, big hits, timpani, risers (also: "cinematic")
         tense      sub heartbeat pulse, dissonant cluster, ticking, slow risers (also: "thriller")
         dark       low drones, sub and noise swells
         sad        slow piano arpeggio with a soft string pad
         mystery    glassy bells over a drone in a phrygian mode
         triumph    brass fanfare, march snare, timpani, bright strings
         adventure  driving plucked strings, toms and brass accents

music_track(sections, total) builds one track that changes style where the story changes:
sections = [(start_s, end_s, style), ...]; neighbouring styles are cross-faded.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000

ALIASES = {"cinematic": "epic", "thriller": "tense", "horror": "dark", "sorrow": "sad", "victory": "triumph",
           "battle": "war", "action": "war", "documentary": "serious", "historical": "epic", "history": "epic"}
CLASSIC = ("calm", "warm", "wonder", "serious")
STYLES = ("calm", "warm", "wonder", "serious", "war", "epic", "tense", "dark", "sad", "mystery", "triumph", "adventure")

# loudness of each style relative to the gentle beds (dB): the heavier ones are a little louder
STYLE_GAIN_DB = {"war": 1.5, "epic": 1.0, "triumph": 1.0, "adventure": 0.5, "tense": 0.0, "dark": 0.0,
                 "sad": 1.0, "mystery": 2.0, "calm": 0.0, "warm": 0.0, "wonder": 0.0, "serious": 0.0}
TARGET_RMS_DB = -23.5


def canon(style: str) -> str:
    s = (style or "warm").lower().strip()
    s = ALIASES.get(s, s)
    return s if s in STYLES else "warm"


# ----------------------------------------------------------------------------- tiny synth kit

def _f(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _lp(x, fc, order=2):
    fc = min(fc, SR * 0.45)
    return sosfilt(butter(order, fc / (SR / 2), "low", output="sos"), x, axis=0).astype(np.float32)


def _hp(x, fc, order=2):
    return sosfilt(butter(order, fc / (SR / 2), "high", output="sos"), x, axis=0).astype(np.float32)


def _bp(x, lo, hi):
    return sosfilt(butter(2, [lo / (SR / 2), min(hi, SR * 0.45) / (SR / 2)], "band", output="sos"), x, axis=0).astype(np.float32)


def _t(n):
    return np.arange(n, dtype=np.float32) / SR


def _env(n, a, r, hold=None):
    t = _t(n)
    e = np.minimum(1.0, t / max(a, 1e-3))
    end = n / SR
    e = e * np.clip((end - t) / max(r, 1e-3), 0, 1)
    return e.astype(np.float32)


def _saw(f, n, detune=(0.0,), phase=0.0):
    t = _t(n)
    out = np.zeros(n, np.float32)
    for d in detune:
        fr = f * 2 ** (d / 1200.0)
        out += 2 * ((fr * t + phase + d * 0.37) % 1.0) - 1
    return out / len(detune)


def _sine(f, n):
    return np.sin(2 * np.pi * f * _t(n)).astype(np.float32)


def _pad(chord, n, bright=1800, a=0.7, r=0.7, octave=0, vib=0.0, gain=0.12):
    x = np.zeros(n, np.float32)
    for m in chord:
        x += _saw(_f(m + octave), n, (-9, 0, 8))
    x = _lp(x, bright)
    if vib:
        x *= (1 + vib * np.sin(2 * np.pi * 5.0 * _t(n))).astype(np.float32)
    return x * _env(n, a, r) * gain / max(1, len(chord) ** 0.5)


def _pluck(m, n, decay=5.5, gain=0.12, bright=1.0):
    t = _t(n)
    f = _f(m)
    x = (np.sin(2 * np.pi * f * t) + 0.35 * bright * np.sin(2 * np.pi * 2 * f * t) + 0.12 * bright * np.sin(2 * np.pi * 3 * f * t))
    return (x * np.exp(-t * decay) * gain).astype(np.float32)


def _piano(m, n, gain=0.14):
    t = _t(n)
    f = _f(m)
    x = np.zeros(n, np.float32)
    for k, a in enumerate((1.0, 0.5, 0.28, 0.16, 0.09), start=1):
        x += a * np.sin(2 * np.pi * f * k * t * (1 + 0.0004 * k * k)) * np.exp(-t * (1.1 + 0.9 * k))
    x *= np.minimum(1, t / 0.005)
    return (x * gain).astype(np.float32)


def _bell(m, n, gain=0.07, decay=2.2):
    t = _t(n)
    f = _f(m)
    x = np.zeros(n, np.float32)
    for r_, a in ((1, 1.0), (2.76, 0.5), (5.4, 0.28), (8.93, 0.14)):
        x += a * np.sin(2 * np.pi * f * r_ * t) * np.exp(-t * decay * (0.7 + 0.35 * r_))
    return (x * gain).astype(np.float32)


def _stab(chord, n, gain=0.14, octave=0):
    """Short brass-like stab: detuned saws with a filter that opens and closes."""
    x = np.zeros(n, np.float32)
    for m in chord:
        x += _saw(_f(m + octave), n, (-12, 0, 11))
    half = n // 2
    a = _lp(x, 2400)
    b = _lp(x, 700)
    mix = np.linspace(1, 0, n).astype(np.float32) ** 1.5
    y = a * mix + b * (1 - mix)
    return y * _env(n, 0.035, 0.25) * gain / max(1, len(chord) ** 0.5)


def _noise(n, rng):
    return rng.standard_normal(n).astype(np.float32)


def _kick(n=None, gain=0.55):
    n = n or int(0.45 * SR)
    t = _t(n)
    f = 45 + 80 * np.exp(-t * 28)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * gain).astype(np.float32)


def _taiko(rng, gain=0.6, pitch=62, length=0.9):
    n = int(length * SR)
    t = _t(n)
    f = pitch + 40 * np.exp(-t * 22)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.5) * 0.55
    skin = _lp(_noise(n, rng), 2200) * np.exp(-t * 26) * 0.7
    return ((body + skin) * gain).astype(np.float32)


def _snare(rng, gain=0.25, length=0.22):
    n = int(length * SR)
    t = _t(n)
    nz = _bp(_noise(n, rng), 1200, 7500) * np.exp(-t * 20)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28) * 0.5
    return ((nz + tone) * gain).astype(np.float32)


def _swell(rng, n, gain=0.12, rising=True):
    nz = _bp(_noise(n, rng), 2500, 11000)
    e = (np.linspace(0, 1, n) ** 2.2) if rising else (np.linspace(1, 0, n) ** 2)
    return (nz * e * gain).astype(np.float32)


def _riser(rng, n, gain=0.1):
    t = _t(n)
    f = np.linspace(180, 1800, n)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    nz = _bp(_noise(n, rng), 700, 9000)
    e = np.linspace(0, 1, n) ** 2
    return ((tone * 0.4 + nz * 0.7) * e * gain).astype(np.float32)


def _hit(rng, gain=0.5):
    """Cinematic impact: low boom + sub drop + noise crash."""
    n = int(3.2 * SR)
    t = _t(n)
    boom = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-t * 0.9) + 28) / SR) * np.exp(-t * 1.6)
    crash = _hp(_noise(n, rng), 900) * np.exp(-t * 2.4) * 0.35
    return ((boom + crash) * gain).astype(np.float32)


def _reverb(x, rng, seconds=1.8, wet=0.28):
    n = int(seconds * SR)
    t = _t(n)
    ir = np.stack([_noise(n, rng), _noise(n, rng)], 1) * np.exp(-t * (6.5 / seconds))[:, None]
    ir = _lp(ir, 5200)
    ir /= np.abs(ir).sum() ** 0.5 + 1e-6
    wetx = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in (0, 1)], 1).astype(np.float32)
    wetx *= np.sqrt((x ** 2).mean() + 1e-9) / (np.sqrt((wetx ** 2).mean()) + 1e-9)
    return (x * (1 - wet) + wetx * wet).astype(np.float32)


class _Buf:
    def __init__(self, n):
        self.x = np.zeros((n, 2), np.float32)

    def add(self, s, at, pan=0.0, gain=1.0):
        a = int(at * SR)
        if a >= len(self.x) or a < 0:
            return
        e = min(len(self.x), a + len(s))
        seg = s[: e - a] * gain
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        self.x[a:e, 0] += seg * l * 1.414
        self.x[a:e, 1] += seg * r * 1.414


# ----------------------------------------------------------------------------- styles
# every style renders one 8-bar phrase; the phrase repeats for as long as the section lasts,
# with more layers joining over the first phrases and a fill every 4 bars.

def _tri(root, quality):
    third = 3 if quality.startswith("m") else 4
    fifth = 6 if quality == "dim" else 7
    return [root, root + third, root + fifth]


def _phrase(style: str, rng):
    """returns (buffer, bars, bpm)"""
    if style == "war":
        bpm, bars = 104, 8
        beat = 60 / bpm
        prog = [(38, "m"), (34, "M"), (36, "M"), (38, "m"), (38, "m"), (34, "M"), (31, "m"), (33, "M")]
        buf = _Buf(int(bars * 4 * beat * SR))
        for b, (root, q) in enumerate(prog):
            t0 = b * 4 * beat
            ch = _tri(root + 24, q)
            # driving low string ostinato (8ths), accented on the beat
            for k in range(8):
                n = int(beat * 0.5 * 0.8 * SR)
                note = root + 12 if k % 4 != 3 else root + 19
                s = _lp(_saw(_f(note), n, (-8, 0, 9)), 520 + 500 * (k % 2 == 0)) * _env(n, 0.01, 0.12)
                buf.add(s, t0 + k * beat / 2, -0.15, 0.22 * (1.25 if k % 2 == 0 else 0.8))
            # sub
            n = int(4 * beat * SR)
            buf.add(_lp(_sine(_f(root), n), 160) * _env(n, 0.05, 0.4), t0, 0, 0.16)
            # string chord and brass stab on the chord change
            n = int(3.8 * beat * SR)
            buf.add(_pad(ch, n, 1500, 0.9, 0.6, gain=0.10), t0, 0.1)
            if b % 4 in (0, 2):
                m = int(1.6 * beat * SR)
                buf.add(_stab([root + 24, root + 31, root + 36 if q == "M" else root + 35 - 0], m, 0.16), t0, 0.3)
            # taiko: 1 and 3 (the 2 and 4 are lighter), fill into every 4th bar
            buf.add(_taiko(rng, 0.62, 58), t0, 0, 1)
            buf.add(_taiko(rng, 0.5, 66), t0 + 2 * beat, 0, 1)
            buf.add(_taiko(rng, 0.28, 74), t0 + 3 * beat, 0.2, 1)
            if b % 4 == 3:
                for k in range(4):
                    buf.add(_taiko(rng, 0.34 + 0.07 * k, 70 - 4 * k, 0.4), t0 + 3 * beat + k * beat / 4, 0, 1)
            if b >= 4:  # march snare, 16ths ghost notes
                for k in range(16):
                    if k % 4 in (0, 2) or k % 4 == 3:
                        buf.add(_snare(rng, 0.14 if k % 4 else 0.22), t0 + k * beat / 4, -0.2, 1)
            if b in (3, 7):
                buf.add(_swell(rng, int(4 * beat * SR), 0.16), t0, 0, 1)
        return buf.x, bars, bpm
    if style == "epic":
        bpm, bars = 76, 8
        beat = 60 / bpm
        prog = [(33, "m"), (29, "M"), (36, "M"), (31, "M")] * 2
        buf = _Buf(int(bars * 4 * beat * SR))
        for b, (root, q) in enumerate(prog):
            t0 = b * 4 * beat
            ch = _tri(root + 24, q)
            n = int(4 * beat * SR)
            buf.add(_pad(ch + [root + 36], n, 2200, 1.2, 1.0, gain=0.12), t0, -0.1)
            buf.add(_pad(_tri(root + 36, q), n, 1500, 1.6, 1.0, vib=0.01, gain=0.07, octave=0), t0, 0.15)
            buf.add(_lp(_sine(_f(root), n), 200) * _env(n, 0.08, 0.6), t0, 0, 0.14)
            for k in range(4):  # low cello pulse
                m = int(beat * 0.9 * SR)
                buf.add(_lp(_saw(_f(root + 12), m, (-6, 6)), 700) * _env(m, 0.02, 0.4), t0 + k * beat, 0, 0.15)
            if b >= 2:  # high strings arpeggio (16ths)
                arp = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[1] + 24]
                for k in range(16):
                    m = int(beat / 4 * 1.2 * SR)
                    buf.add(_lp(_saw(_f(arp[k % 4] + 12), m, (-7, 7)), 2800) * _env(m, 0.01, 0.1), t0 + k * beat / 4, 0.35 * (-1) ** k, 0.085)
            if b % 2 == 0:
                buf.add(_taiko(rng, 0.5, 52, 1.4), t0, 0, 1)
            if b == 0:
                buf.add(_hit(rng, 0.45), t0, 0, 1)
            if b == 7:
                buf.add(_riser(rng, int(4 * beat * SR), 0.18), t0, 0, 1)
        return buf.x, bars, bpm
    if style == "tense":
        bpm, bars = 88, 8
        beat = 60 / bpm
        buf = _Buf(int(bars * 4 * beat * SR))
        roots = [40, 40, 41, 40, 40, 43, 41, 40]
        for b, root in enumerate(roots):
            t0 = b * 4 * beat
            n = int(4 * beat * SR)
            cl = [root + 24, root + 25, root + 30, root + 36]    # root, minor 2nd, tritone: uneasy cluster
            buf.add(_pad(cl, n, 650, 1.5, 1.2, gain=0.1), t0, 0, 1)
            for k in range(4):  # sub heartbeat: two soft thumps per beat pair
                buf.add(_kick(gain=0.16), t0 + k * beat, 0, 1)
                buf.add(_kick(gain=0.10), t0 + k * beat + 0.28, 0, 1)
            if b >= 2:
                for k in range(8):  # ticking
                    m = int(0.03 * SR)
                    buf.add(_hp(_noise(m, rng), 2500) * np.exp(-_t(m) * 120) * 0.12, t0 + k * beat / 2, 0.5 * (-1) ** k, 1)
            if b % 4 == 3:
                buf.add(_riser(rng, int(4 * beat * SR), 0.06), t0, 0, 1)
            if b == 4:
                buf.add(_bell(root + 36, int(3 * SR), 0.05, 1.5), t0 + beat, 0.4, 1)
        return buf.x, bars, bpm
    if style == "dark":
        bpm, bars = 60, 8
        beat = 1.0
        buf = _Buf(int(bars * 4 * beat * SR))
        for b in range(bars):
            t0 = b * 4.0
            n = int(4.0 * SR)
            root = 36 if b % 4 < 2 else 35
            buf.add(_pad([root + 12, root + 19, root + 24], n, 420, 1.5, 1.5, gain=0.16), t0, 0)
            buf.add(_lp(_sine(_f(root), n), 120) * _env(n, 0.5, 1.5), t0, 0, 0.14)
            buf.add(_pad([root + 36, root + 37, root + 42], n, 1100, 2.0, 1.5, vib=0.02, gain=0.05), t0, 0.2)
            if b % 2 == 1:
                buf.add(_swell(rng, n, 0.10), t0, 0, 1)
        buf.add(_hit(rng, 0.35), 0, 0, 1)
        return buf.x, bars, bpm
    if style == "sad":
        bpm, bars = 60, 8
        beat = 1.0
        buf = _Buf(int(bars * 4 * beat * SR))
        prog = [(57, "m"), (53, "M"), (50, "m"), (52, "M")] * 2
        for b, (root, q) in enumerate(prog):
            t0 = b * 4.0
            ch = _tri(root, q)
            n = int(4.0 * SR)
            buf.add(_pad([c + 12 for c in ch], n, 1100, 1.4, 1.2, vib=0.008, gain=0.09), t0, 0.1)
            buf.add(_lp(_saw(_f(root - 12), n, (-5, 5)), 420) * _env(n, 0.6, 1.2), t0, 0, 0.13)
            pat = [ch[0], ch[1], ch[2], ch[1] + 12, ch[2], ch[1], ch[0] + 12, ch[2]]
            for k, m in enumerate(pat):
                buf.add(_piano(m + 12, int(3.0 * SR), 0.13 if k % 4 == 0 else 0.095), t0 + k * 0.5, (k % 3 - 1) * 0.15, 1)
        return buf.x, bars, bpm
    if style == "mystery":
        bpm, bars = 66, 8
        beat = 60 / bpm
        buf = _Buf(int(bars * 4 * beat * SR))
        scale = [62, 63, 67, 69, 70, 74, 75, 79]     # D phrygian-ish
        order = rng.integers(0, len(scale), 64)
        for b in range(bars):
            t0 = b * 4 * beat
            n = int(4 * beat * SR)
            root = 38 if b % 4 < 3 else 39
            buf.add(_pad([root + 12, root + 19, root + 24], n, 650, 1.6, 1.4, gain=0.14), t0, 0)
            buf.add(_lp(_sine(_f(root), n), 140) * _env(n, 0.6, 1.4), t0, 0, 0.12)
            for k in range(4):
                if rng.random() < 0.75:
                    buf.add(_bell(int(scale[order[b * 8 + k]]) + 12, int(3.6 * SR), 0.06, 1.7), t0 + (k + rng.random() * 0.3) * beat,
                            float(rng.uniform(-0.6, 0.6)), 1)
        return buf.x, bars, bpm
    if style == "triumph":
        bpm, bars = 108, 8
        beat = 60 / bpm
        prog = [(48, "M"), (43, "M"), (45, "m"), (41, "M"), (48, "M"), (43, "M"), (41, "M"), (43, "M")]
        buf = _Buf(int(bars * 4 * beat * SR))
        for b, (root, q) in enumerate(prog):
            t0 = b * 4 * beat
            ch = _tri(root + 24, q)
            n = int(4 * beat * SR)
            buf.add(_pad(ch + [root + 36], n, 2600, 0.5, 0.5, gain=0.11), t0, 0)
            buf.add(_lp(_sine(_f(root), n), 200) * _env(n, 0.03, 0.4), t0, 0, 0.14)
            fan = [0, 7, 12, 16, 19, 16, 12, 7]
            for k in (0, 1, 2, 4, 6):    # fanfare figure
                m = int((0.75 if k in (0, 4) else 0.4) * beat * SR)
                buf.add(_stab([root + 12 + fan[k], root + 19 + fan[k]], m, 0.13), t0 + k * beat / 2, 0.25, 1)
            for k in range(4):
                buf.add(_snare(rng, 0.16 if k % 2 == 0 else 0.22), t0 + k * beat, -0.2, 1)
            buf.add(_taiko(rng, 0.5, 60), t0, 0, 1)
            buf.add(_taiko(rng, 0.4, 66), t0 + 2 * beat, 0, 1)
            for k in range(8):   # bright shimmer
                buf.add(_bell(root + 36 + [0, 4, 7, 12][k % 4], int(1.4 * SR), 0.03, 3.2), t0 + k * beat / 2, 0.5 * (-1) ** k, 1)
            if b in (3, 7):
                buf.add(_swell(rng, int(4 * beat * SR), 0.13), t0, 0, 1)
        return buf.x, bars, bpm
    if style == "adventure":
        bpm, bars = 116, 8
        beat = 60 / bpm
        prog = [(50, "M"), (45, "M"), (47, "m"), (43, "M")] * 2
        buf = _Buf(int(bars * 4 * beat * SR))
        for b, (root, q) in enumerate(prog):
            t0 = b * 4 * beat
            ch = _tri(root + 24, q)
            n = int(4 * beat * SR)
            buf.add(_pad(ch, n, 1900, 0.5, 0.5, gain=0.09), t0, 0.1)
            for k in range(16):
                m = [ch[0], ch[2], ch[1], ch[2]][k % 4]
                buf.add(_pluck(m + 12, int(0.55 * SR), 7.5, 0.1), t0 + k * beat / 4 * 1.0 if k < 16 else t0, 0.3 * (-1) ** k, 1)
            buf.add(_lp(_saw(_f(root), int(beat * 0.9 * SR), (-6, 6)), 480) * _env(int(beat * 0.9 * SR), 0.01, 0.2), t0, 0, 0.28)
            buf.add(_lp(_saw(_f(root), int(beat * 0.9 * SR), (-6, 6)), 480) * _env(int(beat * 0.9 * SR), 0.01, 0.2), t0 + 2 * beat, 0, 0.22)
            buf.add(_taiko(rng, 0.42, 66, 0.6), t0, 0, 1)
            buf.add(_taiko(rng, 0.3, 80, 0.4), t0 + 1.5 * beat, 0.2, 1)
            buf.add(_taiko(rng, 0.34, 72, 0.5), t0 + 3 * beat, -0.2, 1)
            if b % 2 == 0:
                buf.add(_stab([root + 24, root + 28 if q == "M" else root + 27], int(1.2 * beat * SR), 0.1), t0, 0.3, 1)
        return buf.x, bars, bpm
    raise KeyError(style)


# ----------------------------------------------------------------------------- public API

def _render_style(style: str, dur: float, seed: int = 0) -> np.ndarray:
    """Stereo track of the style, `dur` seconds long, normalised to the common music loudness."""
    style = canon(style)
    n_out = int(dur * SR)
    if style in CLASSIC:
        from .music_classic import music_bed
        x = music_bed(dur, "warm" if style == "calm" else style)
    else:
        rng = np.random.default_rng(seed * 101 + sum(map(ord, style)))
        phrase, bars, bpm = _phrase(style, rng)
        # layers come in over the first phrase: scale the whole phrase up from a soft start
        reps = int(np.ceil(dur * SR / len(phrase))) + 1
        tiled = np.tile(phrase, (reps, 1))[: n_out + SR]
        ramp = np.minimum(1.0, 0.55 + 0.45 * np.arange(len(tiled)) / (min(len(tiled), len(phrase)) * 0.9)).astype(np.float32)
        x = tiled * ramp[:, None]
        x = _reverb(x, rng, 1.6 if style != "sad" else 2.4, 0.22 if style in ("war", "tense", "adventure") else 0.3)
        x = x[:n_out]
        fade = int(min(2.0, dur / 5) * SR)
        if fade > 1:
            x[:fade] *= np.linspace(0, 1, fade)[:, None] ** 1.5
            x[-fade:] *= np.linspace(1, 0, fade)[:, None]
    x = x.astype(np.float32)
    # judge loudness on what small speakers actually play (above ~130 Hz); sub bass alone must not set the level
    ref = _bp(x, 250, 5000)
    rms = float(np.sqrt((ref ** 2).mean()) + 1e-9)
    target = 10 ** ((TARGET_RMS_DB + STYLE_GAIN_DB.get(style, 0.0) - 2.0) / 20)
    x *= target / rms
    full = float(np.sqrt((x ** 2).mean()) + 1e-9)
    cap = 10 ** ((TARGET_RMS_DB + STYLE_GAIN_DB.get(style, 0.0) + 2.0) / 20)
    if full > cap:
        x *= cap / full
    peak = float(np.abs(x).max())
    if peak > 0.9:
        x *= 0.9 / peak
    return x.astype(np.float32)


def music_track(sections: list[tuple[float, float, str]], total: float, xfade: float = 2.5, seed: int = 0) -> np.ndarray:
    """One track for the whole video. sections = [(start, end, style)]; touching sections of the same
    style are merged and the others are cross-faded over `xfade` seconds."""
    merged: list[list] = []
    for s, e, st in sections:
        st = canon(st)
        if merged and merged[-1][2] == st:
            merged[-1][1] = e
        else:
            merged.append([s, e, st])
    if not merged:
        merged = [[0.0, total, "warm"]]
    merged[0][0] = 0.0
    merged[-1][1] = total
    out = np.zeros((int(total * SR) + 1, 2), np.float32)
    for i, (s, e, st) in enumerate(merged):
        pad_in = xfade / 2 if i else 0.0
        pad_out = xfade / 2 if i < len(merged) - 1 else 0.0
        a, b = max(0.0, s - pad_in), min(total, e + pad_out)
        seg = _render_style(st, b - a + 0.1, seed + i)[: int((b - a) * SR)]
        n = len(seg)
        env = np.ones(n, np.float32)
        fi, fo = int(pad_in * 2 * SR), int(pad_out * 2 * SR)
        if fi > 1:
            env[:fi] = np.sin(np.linspace(0, np.pi / 2, fi)) ** 1
        if fo > 1:
            env[-fo:] = np.cos(np.linspace(0, np.pi / 2, fo)) ** 1
        i0 = int(a * SR)
        out[i0: i0 + n] += seg * env[:, None]
    out = out[: int(total * SR)]
    fade = int(min(3.0, total / 4) * SR)
    if fade > 1:
        out[:fade] *= np.linspace(0, 1, fade)[:, None]
        out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return out


def music_bed(total: float, mood: str = "warm", bpm: int = 84) -> np.ndarray:
    """Single style for the whole video (kept for older projects)."""
    return music_track([(0.0, total, mood)], total)
