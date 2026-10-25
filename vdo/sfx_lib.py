"""Built-in sound library, synthesised in code (no files, no licences).

Every function returns stereo float32 at 48 kHz, peak-normalised; loudness is set later by LEVELS.
Names (see NAMES at the bottom) are what scripts / project.json use: "sfx": ["cheer"], "ambience": "market".
"""

from __future__ import annotations

import numpy as np
from scipy import signal

SR = 48000


# --------------------------------------------------------------------------- building blocks

def _t(d):
    return np.arange(int(d * SR)) / SR


def _noise(n, rng):
    return rng.standard_normal(n).astype(np.float32)


def _pink(n, rng):
    """Pink-ish noise (softer, more natural than white)."""
    w = rng.standard_normal(n)
    spec = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = 1
    spec /= np.sqrt(f / 100.0)
    return np.fft.irfft(spec, n).astype(np.float32)


def _bp(x, lo, hi, order=2):
    sos = signal.butter(order, [max(20, lo), min(hi, SR / 2 - 100)], btype="band", fs=SR, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def _lp(x, f, order=2):
    sos = signal.butter(order, min(f, SR / 2 - 100), btype="low", fs=SR, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def _hp(x, f, order=2):
    sos = signal.butter(order, max(20, f), btype="high", fs=SR, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def _env(n, a, r, hold=0.0, curve=2.0):
    t = np.arange(n) / SR
    up = np.clip(t / max(a, 1e-4), 0, 1)
    down = np.clip(((n / SR) - t) / max(r, 1e-4), 0, 1) ** curve if r else 1.0
    return (up * down).astype(np.float32)


def _decay(n, k):
    return np.exp(-np.arange(n) / SR * k).astype(np.float32)


def _reverb(x, size=1.2, mix=0.25, rng=None, damp=4000):
    """Small convolution reverb: exponentially decaying filtered noise."""
    rng = rng or np.random.default_rng(1)
    n = int(size * SR)
    ir = _lp(_noise(n, rng), damp) * np.exp(-np.arange(n) / SR * (6.0 / size))
    ir[0] = 0
    ir /= np.sqrt((ir ** 2).sum()) + 1e-9
    wet = signal.fftconvolve(x, ir)[: len(x) + n // 2]
    dry = np.concatenate([x, np.zeros(len(wet) - len(x), np.float32)])
    return (dry * (1 - mix) + wet * mix).astype(np.float32)


def _place(buf, x, at):
    i = int(at * SR)
    if i >= len(buf) or i + len(x) <= 0:
        return
    j = min(len(buf), i + len(x))
    s = max(0, -i)
    buf[max(0, i):j] += x[s: s + j - max(0, i)]


def _stereo(x, width=0.0, rng=None, pan=0.0):
    """Mono -> stereo with optional constant pan and decorrelated width."""
    l = x * np.cos((pan + 1) * np.pi / 4)
    r = x * np.sin((pan + 1) * np.pi / 4)
    if width:
        d = int(0.011 * SR)
        r = np.concatenate([np.zeros(d, np.float32), r[:-d]]) * (1 - width * 0.3) + r * width * 0.3
    return np.stack([l, r], 1).astype(np.float32)


def _mix_stereo(n, items):
    """items: [(mono, at, pan)] -> stereo buffer of n samples."""
    out = np.zeros((n, 2), np.float32)
    for x, at, pan in items:
        i = int(at * SR)
        if i >= n:
            continue
        x = x[: n - i]
        out[i:i + len(x), 0] += x * np.cos((pan + 1) * np.pi / 4)
        out[i:i + len(x), 1] += x * np.sin((pan + 1) * np.pi / 4)
    return out


def _norm(x, peak=0.9):
    m = float(np.max(np.abs(x))) or 1.0
    return (x * (peak / m)).astype(np.float32)


def _fade(x, a=0.02, b=0.08):
    n = len(x)
    fa, fb = min(n, int(a * SR)), min(n, int(b * SR))
    if fa:
        x[:fa] *= np.linspace(0, 1, fa)[:, None] if x.ndim == 2 else np.linspace(0, 1, fa)
    if fb:
        x[-fb:] *= np.linspace(1, 0, fb)[:, None] if x.ndim == 2 else np.linspace(1, 0, fb)
    return x


# --------------------------------------------------------------------------- voices (formant synthesis)

VOWELS = {  # formant (freq, bandwidth) pairs
    "a": [(800, 80), (1150, 90), (2900, 120)],
    "e": [(400, 60), (1700, 90), (2600, 100)],
    "i": [(300, 50), (2200, 100), (3000, 120)],
    "o": [(450, 70), (800, 80), (2830, 100)],
    "u": [(325, 50), (700, 60), (2530, 100)],
    "ae": [(660, 80), (1700, 90), (2400, 100)],
}


def _glottal(f0, rng, breath=0.15):
    """Band-limited glottal pulse train following the pitch curve f0 (array)."""
    ph = np.cumsum(f0) / SR
    saw = 2 * (ph % 1.0) - 1
    src = _lp(saw.astype(np.float32), 4000) + breath * _noise(len(f0), rng)
    return src


def voice(dur, f0_start, f0_end, vowel="a", rng=None, vibrato=0.0, rough=0.0, curve=1.0, breath=0.15):
    rng = rng or np.random.default_rng(0)
    t = _t(dur)
    p = (t / dur) ** curve
    f0 = f0_start + (f0_end - f0_start) * p
    if vibrato:
        f0 = f0 * (1 + vibrato * np.sin(2 * np.pi * rng.uniform(5, 7) * t))
    f0 = f0 * (1 + rough * _lp(_noise(len(t), rng), 30) * 0.2)
    src = _glottal(f0, rng, breath)
    out = np.zeros_like(src)
    for k, (f, bw) in enumerate(VOWELS[vowel]):
        f = f * rng.uniform(0.92, 1.1) * (1.15 if f0_start > 230 else 1.0)
        out += _bp(src, f - bw, f + bw) * (1.0, 0.6, 0.25)[k]
    return out * _env(len(t), 0.04, 0.12)


# --------------------------------------------------------------------------- soft UI / transitions

def air_soft(rng):
    """Very gentle airy swell for scene changes (replaces the old whoosh)."""
    t = _t(0.85)
    x = _bp(_pink(len(t), rng), 300, 2200)
    env = np.sin(np.pi * np.clip(t / 0.85, 0, 1)) ** 3
    return _stereo(_norm(x * env, 0.5), width=0.6)


def chime_soft(rng):
    """Soft two-note chime (alternative scene-change sound)."""
    n = int(1.6 * SR)
    out = np.zeros(n, np.float32)
    base = rng.choice([659.3, 587.3, 523.3, 784.0])
    for k, (f, at) in enumerate([(base, 0.0), (base * 1.5, 0.09)]):
        t = _t(1.4)
        tone = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t * 6)) * np.exp(-t * 3.2)
        _place(out, (tone * (0.8 if k else 1.0)).astype(np.float32), at)
    return _stereo(_norm(_reverb(out, 1.4, 0.35, rng)[:n], 0.5), width=0.5)


def paper_soft(rng):
    """Light paper swipe."""
    t = _t(0.35)
    x = _bp(_noise(len(t), rng), 1500, 7000) * np.sin(np.pi * t / 0.35) ** 2
    x += _bp(_noise(len(t), rng), 300, 900) * 0.3 * np.sin(np.pi * t / 0.35) ** 4
    return _stereo(_norm(x, 0.45), width=0.4)


def pop_soft(rng):
    """Rounded, friendly 'bloop' for pop-ups (much softer than a click-pop)."""
    t = _t(0.16)
    f0 = rng.uniform(440, 560)
    f = f0 * np.exp(-t * 9) + f0 * 0.45
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.18 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    x = x * _env(len(t), 0.004, 0.13, curve=1.6)
    x = _lp(x.astype(np.float32), 2600)
    return _stereo(_norm(_reverb(x, 0.4, 0.15, rng)[: len(x) + 2400], 0.55))


def slide_soft(rng):
    t = _t(0.32)
    sweep = np.linspace(0, 1, len(t))
    x = _bp(_pink(len(t), rng), 500, 2600) * np.sin(np.pi * sweep) ** 2
    return _stereo(_norm(x, 0.4), width=0.5)


def step_soft(rng):
    t = _t(0.09)
    x = _lp(_noise(len(t), rng), 900) * _decay(len(t), 60) + 0.6 * np.sin(2 * np.pi * rng.uniform(90, 130) * t) * _decay(len(t), 45)
    return _stereo(_norm(x.astype(np.float32), 0.4))


def sparkle(rng):
    n = int(1.6 * SR)
    out = np.zeros(n, np.float32)
    scale = [1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0]
    for k in range(9):
        f = scale[int(rng.integers(0, len(scale)))] * rng.choice([1, 2])
        t = _t(0.6)
        _place(out, (np.sin(2 * np.pi * f * t) * np.exp(-t * 9) * rng.uniform(0.4, 1)).astype(np.float32), k * 0.07)
    return _stereo(_norm(_reverb(out, 1.2, 0.4, rng)[:n], 0.5), width=0.8)


# --------------------------------------------------------------------------- people

def _clap(rng):
    t = _t(0.06)
    x = _bp(_noise(len(t), rng), rng.uniform(700, 1100), rng.uniform(2200, 3600)) * _decay(len(t), rng.uniform(70, 110))
    return x


def applause(rng, dur=4.5):
    n = int(dur * SR)
    items = []
    people = 28
    for p in range(people):
        rate = rng.uniform(3.2, 5.0)
        start = rng.uniform(0, 0.6)
        stop = dur - rng.uniform(0.2, 1.4)
        tt = start
        pan = rng.uniform(-0.8, 0.8)
        g = rng.uniform(0.4, 1.0)
        while tt < stop:
            items.append((_clap(rng) * g, tt, pan))
            tt += 1 / rate * rng.uniform(0.9, 1.1)
    out = _mix_stereo(n, items)
    env = np.minimum(1, _t(dur) / 0.5) * np.clip((dur - _t(dur)) / 1.2, 0, 1)
    out *= env[:, None]
    out = np.stack([_reverb(out[:, 0], 0.9, 0.25, rng)[:n], _reverb(out[:, 1], 0.9, 0.25, rng)[:n]], 1)
    return _norm(out, 0.85)


def cheer(rng, dur=3.5, applause_mix=0.5):
    """Crowd cheering 'yaaay' / 'hooray' with whistles and some clapping."""
    n = int(dur * SR)
    items = []
    for k in range(26):
        female = rng.random() < 0.45
        f0 = rng.uniform(220, 330) if female else rng.uniform(120, 190)
        d = rng.uniform(1.0, 2.3)
        at = rng.uniform(0, 0.5) + (rng.uniform(0, 1.0) if rng.random() < 0.4 else 0)
        vow = rng.choice(["a", "e", "ae", "o"])
        v = voice(d, f0 * 1.0, f0 * rng.uniform(1.15, 1.45), vow, rng, vibrato=0.02, rough=0.4, curve=0.5, breath=0.25)
        items.append((v * rng.uniform(0.5, 1.0), at, rng.uniform(-0.8, 0.8)))
    for k in range(3):  # whistles
        t = _t(rng.uniform(0.5, 0.9))
        f = rng.uniform(1800, 2400) * (1 + 0.15 * np.sin(np.pi * t / t[-1]))
        w = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(len(t), 0.05, 0.2) * 0.35
        items.append((w.astype(np.float32), rng.uniform(0.3, dur - 1), rng.uniform(-0.6, 0.6)))
    out = _mix_stereo(n, items)
    out = np.stack([_reverb(out[:, 0], 1.0, 0.3, rng)[:n], _reverb(out[:, 1], 1.0, 0.3, rng)[:n]], 1)
    if applause_mix:
        out = _norm(out, 0.8) + applause(rng, dur) * applause_mix
    return _fade(_norm(out, 0.9), 0.05, 0.9)


def celebration(rng, dur=5.0):
    out = cheer(rng, dur, applause_mix=0.7)
    # festive hand drum + tambourine pattern
    n = len(out)
    beat = 60 / 120
    drum = np.zeros(n, np.float32)
    for i in range(int(dur / beat * 2)):
        at = i * beat / 2
        t = _t(0.25)
        if i % 2 == 0:
            _place(drum, (np.sin(2 * np.pi * (110 * np.exp(-t * 8) + 70) * t) * _decay(len(t), 14)).astype(np.float32), at)
        tam = _bp(_noise(int(0.12 * SR), rng), 6000, 12000) * _decay(int(0.12 * SR), 30) * 0.4
        _place(drum, tam, at + 0.01)
    return _norm(out + _stereo(_norm(drum, 0.5)) * 0.6, 0.9)


def gasp_crowd(rng):
    dur = 1.4
    n = int(dur * SR)
    items = []
    for k in range(18):
        f0 = rng.uniform(140, 300)
        v = voice(rng.uniform(0.5, 0.9), f0 * 1.25, f0 * 0.8, "o", rng, breath=0.5, curve=0.7)
        items.append((v * rng.uniform(0.5, 1), rng.uniform(0, 0.15), rng.uniform(-0.7, 0.7)))
    return _fade(_norm(_mix_stereo(n, items), 0.8))


def laugh_crowd(rng):
    dur = 2.6
    n = int(dur * SR)
    items = []
    for k in range(14):
        f0 = rng.uniform(130, 300)
        at = rng.uniform(0, 0.4)
        for j in range(int(rng.integers(4, 8))):
            v = voice(0.11, f0 * (1.1 - 0.04 * j), f0 * (0.95 - 0.04 * j), "a", rng, breath=0.45)
            items.append((v * (1 - j * 0.08), at + j * rng.uniform(0.15, 0.19), rng.uniform(-0.7, 0.7)))
    out = _mix_stereo(n, items)
    return _fade(_norm(np.stack([_reverb(out[:, 0], 0.8, 0.2, rng)[:n], _reverb(out[:, 1], 0.8, 0.2, rng)[:n]], 1), 0.8))


def scream(rng):
    female = rng.random() < 0.6
    f0 = rng.uniform(520, 700) if female else rng.uniform(330, 440)
    d = rng.uniform(1.1, 1.5)
    v = voice(d, f0, f0 * rng.uniform(0.75, 0.9), "a", rng, vibrato=0.035, rough=1.2, curve=1.4, breath=0.35)
    v = v + 0.3 * voice(d, f0 * 1.01, f0 * 0.8, "ae", rng, vibrato=0.04, rough=1.4, breath=0.4)
    v = _reverb(v, 1.3, 0.3, rng)
    return _fade(_stereo(_norm(v, 0.85), width=0.4))


def shout_crowd(rng, dur=3.0, intensity=1.0):
    n = int(dur * SR)
    items = []
    for k in range(int(22 * intensity)):
        f0 = rng.uniform(130, 230)
        at = rng.uniform(0, dur - 0.5)
        v = voice(rng.uniform(0.3, 0.8), f0 * 1.2, f0 * rng.uniform(0.8, 1.1), rng.choice(["a", "o", "e"]), rng,
                  rough=0.9, breath=0.3)
        items.append((v * rng.uniform(0.4, 1), at, rng.uniform(-0.8, 0.8)))
    return _mix_stereo(n, items)


def chaos(rng, dur=4.0):
    """Panic: shouting crowd, screams, running feet, crashes."""
    n = int(dur * SR)
    out = _norm(shout_crowd(rng, dur, 1.3), 0.7)
    for k in range(3):
        s = scream(rng) * rng.uniform(0.35, 0.6)
        i = int(rng.uniform(0.1, dur - 1.6) * SR)
        out[i:i + len(s)] += s[: n - i]
    feet = np.zeros(n, np.float32)
    for k in range(60):
        st = step_soft(rng)[:, 0] * rng.uniform(0.4, 1)
        _place(feet, st, rng.uniform(0, dur - 0.1))
    out += _stereo(feet, width=0.7) * 0.6
    for k in range(2):
        c = crash(rng) * 0.5
        i = int(rng.uniform(0.3, dur - 1.0) * SR)
        out[i:i + len(c)] += c[: n - i]
    return _fade(_norm(out, 0.9), 0.1, 0.8)


# --------------------------------------------------------------------------- war

def sword_clash(rng):
    t = _t(1.3)
    partials = np.array([1210, 2837, 4122, 5650, 7011]) * rng.uniform(0.9, 1.12)
    x = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t * (4 + i * 2)) / (i + 1) for i, f in enumerate(partials))
    x = x + _hp(_noise(len(t), rng), 2000) * np.exp(-t * 70) * 2.5
    return _stereo(_norm(x.astype(np.float32), 0.8), pan=rng.uniform(-0.5, 0.5))


def sword_draw(rng):
    t = _t(0.9)
    scrape = _bp(_noise(len(t), rng), 3000, 9000) * np.clip(1 - t / 0.45, 0, 1) * 0.6
    f = np.linspace(2400, 3600, len(t))
    ring = (np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5 + np.sin(2 * np.pi * np.cumsum(f * 2.7) / SR) * 0.2) * np.exp(-t * 3.5) * np.clip(t / 0.35, 0, 1)
    return _stereo(_norm((scrape + ring).astype(np.float32), 0.7))


def war_drums(rng, dur=4.0, bpm=96):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    beat = 60 / bpm
    pattern = [1, 0, 0.6, 0, 1, 0.5, 0.7, 0]
    i = 0
    while i * beat / 2 < dur:
        g = pattern[i % len(pattern)]
        if g:
            t = _t(0.9)
            body = np.sin(2 * np.pi * (70 * np.exp(-t * 6) + 48) * t) * _decay(len(t), 5)
            skin = _lp(_noise(len(t), rng), 900) * _decay(len(t), 25) * 0.5
            _place(out, ((body + skin) * g).astype(np.float32), i * beat / 2)
        i += 1
    return _fade(_stereo(_norm(_reverb(out, 1.8, 0.35, rng)[:n], 0.9), width=0.5), 0.01, 0.8)


def war_horn(rng):
    d = 2.6
    t = _t(d)
    f0 = rng.uniform(98, 117)
    f = f0 * (1 + 0.03 * np.clip(t / 0.3, 0, 1)) * (1 + 0.006 * np.sin(2 * np.pi * 5 * t))
    saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
    bright = 600 + 1800 * np.clip(t / 0.4, 0, 1)
    x = _lp(saw.astype(np.float32), 1400) * 0.7 + _bp(saw.astype(np.float32), 400, 1600) * 0.4
    x = x * _env(len(t), 0.25, 0.7, curve=1.4)
    return _fade(_stereo(_norm(_reverb(x, 2.0, 0.35, rng)[: len(x) + SR], 0.85), width=0.5))


def arrows(rng):
    dur = 2.0
    n = int(dur * SR)
    items = []
    for k in range(int(rng.integers(5, 9))):
        d = rng.uniform(0.35, 0.6)
        t = _t(d)
        f = np.linspace(rng.uniform(3500, 4500), rng.uniform(1500, 2200), len(t))
        whistle = _bp(_noise(len(t), rng), 1500, 5000) * 0.5 + np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.15
        items.append(((whistle * np.sin(np.pi * t / d) ** 2).astype(np.float32), rng.uniform(0, 1.2), rng.uniform(-0.9, 0.9)))
    for k in range(4):
        t = _t(0.12)
        items.append(((_lp(_noise(len(t), rng), 1500) * _decay(len(t), 45)).astype(np.float32), rng.uniform(0.5, 1.8), rng.uniform(-0.7, 0.7)))
    return _fade(_norm(_mix_stereo(n, items), 0.8))


def battle(rng, dur=4.0):
    """A short burst of battle: shouts, clashes, drums."""
    n = int(dur * SR)
    out = _norm(shout_crowd(rng, dur, 1.2), 0.6)
    for k in range(int(dur * 2.2)):
        c = sword_clash(rng) * rng.uniform(0.3, 0.7)
        i = int(rng.uniform(0, dur - 0.4) * SR)
        out[i:i + len(c)] += c[: n - i]
    out += war_drums(rng, dur)[:n] * 0.45
    return _fade(_norm(out, 0.9), 0.15, 0.9)


def gallop(rng, dur=3.0):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    cycle = 0.42
    tt = 0.0
    while tt < dur - 0.1:
        for off in (0.0, 0.09, 0.17):
            t = _t(0.08)
            hoof = _bp(_noise(len(t), rng), 300, 2500) * _decay(len(t), 55) + 0.5 * np.sin(2 * np.pi * 160 * t) * _decay(len(t), 60)
            _place(out, (hoof * rng.uniform(0.6, 1)).astype(np.float32), tt + off + rng.uniform(-0.01, 0.01))
        tt += cycle
    env = np.clip(_t(dur) / 0.6, 0, 1) * np.clip((dur - _t(dur)) / 0.8, 0, 1)
    return _stereo(_norm(out * env, 0.75), width=0.4)


def march(rng, dur=4.0):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    step = 0.5
    tt = 0.0
    while tt < dur:
        for s in range(12):  # a unit of soldiers, slightly out of sync
            t = _t(0.1)
            st = _lp(_noise(len(t), rng), 1200) * _decay(len(t), 40)
            _place(out, (st * rng.uniform(0.4, 0.9)).astype(np.float32), tt + rng.uniform(-0.02, 0.025))
        jingle = _bp(_noise(int(0.15 * SR), rng), 5000, 11000) * _decay(int(0.15 * SR), 25) * 0.25
        _place(out, jingle, tt + 0.02)
        tt += step
    return _fade(_stereo(_norm(out, 0.75), width=0.5), 0.3, 0.6)


# --------------------------------------------------------------------------- big events

def blast(rng):
    """Explosion: crack, deep boom, rumbling tail, falling debris."""
    d = 4.0
    n = int(d * SR)
    t = _t(d)
    crack = _hp(_noise(n, rng), 800) * np.exp(-t * 35)
    boom_noise = _noise(n, rng)
    cutoff_env = np.exp(-t * 2.2)
    boom = _lp(boom_noise, 2500) * np.exp(-t * 14) + _lp(boom_noise, 400) * np.exp(-t * 2.6) * 1.4
    sub = np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t * 1.5) + 28) / SR) * np.exp(-t * 2.0) * 1.2
    debris = np.zeros(n, np.float32)
    for k in range(40):
        at = rng.uniform(0.4, 2.8)
        m = int(0.05 * SR)
        _place(debris, (_bp(_noise(m, rng), 1500, 6000) * _decay(m, 80) * rng.uniform(0.1, 0.4)).astype(np.float32), at)
    x = crack * 0.8 + boom + sub + debris
    x = _reverb(x.astype(np.float32), 2.5, 0.3, rng)[:n]
    _ = cutoff_env
    return _fade(_stereo(_norm(x, 0.95), width=0.6), 0.0, 1.0)


def crash(rng):
    d = 1.4
    t = _t(d)
    x = _bp(_noise(len(t), rng), 500, 8000) * np.exp(-t * 7) + 0.6 * np.sin(2 * np.pi * 90 * t) * np.exp(-t * 10)
    for k in range(10):
        m = int(0.04 * SR)
        y = np.zeros(len(t), np.float32)
        _place(y, (_hp(_noise(m, rng), 2500) * _decay(m, 90)).astype(np.float32), rng.uniform(0.05, 0.9))
        x = x + y * rng.uniform(0.2, 0.5)
    return _stereo(_norm(x.astype(np.float32), 0.85), pan=rng.uniform(-0.4, 0.4))


def thunder(rng):
    d = 5.0
    n = int(d * SR)
    t = _t(d)
    crack = _hp(_noise(n, rng), 1200) * np.exp(-t * 18) * (t < 0.6)
    rum = _lp(_noise(n, rng), 220) * (np.exp(-t * 0.9) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 0.7 * t + 0.5))))
    x = crack * 0.7 + rum * 2.2
    return _fade(_stereo(_norm(_reverb(x.astype(np.float32), 2.8, 0.3, rng)[:n], 0.9), width=0.8), 0.0, 1.5)


def rumble(rng):
    d = 4.0
    t = _t(d)
    x = _lp(_noise(len(t), rng), 140) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.1 * t) ** 2)
    x = x * np.sin(np.pi * t / d) ** 0.7
    for k in range(12):
        m = int(0.05 * SR)
        y = np.zeros(len(t), np.float32)
        _place(y, (_bp(_noise(m, rng), 800, 4000) * _decay(m, 70)).astype(np.float32), rng.uniform(0.3, d - 0.5))
        x = x + y * 0.25
    return _stereo(_norm(x.astype(np.float32), 0.9), width=0.5)


def fire_burst(rng):
    """Flames catching: soft whoomp + crackle."""
    d = 3.0
    n = int(d * SR)
    t = _t(d)
    whoomp = _lp(_noise(n, rng), 700) * np.clip(t / 0.25, 0, 1) * np.exp(-t * 1.6) * 1.2
    crack = np.zeros(n, np.float32)
    for k in range(70):
        m = int(rng.uniform(0.005, 0.02) * SR)
        _place(crack, (_hp(_noise(m, rng), 1500) * _decay(m, 200) * rng.uniform(0.2, 1)).astype(np.float32), rng.uniform(0.15, d - 0.1))
    x = whoomp + crack * 0.6 * np.clip(t / 0.3, 0, 1)
    return _fade(_stereo(_norm(x.astype(np.float32), 0.85), width=0.6), 0.0, 0.8)


def splash(rng):
    d = 1.6
    t = _t(d)
    x = _bp(_noise(len(t), rng), 400, 6000) * np.exp(-t * 5) * np.clip(t / 0.02, 0, 1)
    for k in range(25):
        m = int(0.03 * SR)
        y = np.zeros(len(t), np.float32)
        f = rng.uniform(800, 2500)
        tt = _t(0.03)
        _place(y, (np.sin(2 * np.pi * f * (1 + 3 * tt) * tt) * _decay(m, 80)).astype(np.float32), rng.uniform(0.1, 1.2))
        x = x + y * 0.15
    return _stereo(_norm(x.astype(np.float32), 0.8), width=0.5)


# --------------------------------------------------------------------------- things

def bell(rng):
    d = 5.0
    t = _t(d)
    f0 = rng.uniform(196, 262)
    ratios = [0.5, 1.0, 1.183, 1.506, 2.0, 2.514, 2.662, 3.011]
    x = sum(np.sin(2 * np.pi * f0 * r * t) * np.exp(-t * (0.6 + 0.4 * i)) / (1 + 0.4 * i) for i, r in enumerate(ratios))
    x = x * np.clip(t / 0.003, 0, 1)
    return _stereo(_norm(_reverb(x.astype(np.float32), 2.5, 0.3, rng)[: len(t)], 0.75), width=0.6)


def gong(rng):
    d = 5.0
    t = _t(d)
    f0 = rng.uniform(80, 110)
    x = sum(np.sin(2 * np.pi * f0 * r * t * (1 + 0.01 * np.exp(-t * 2))) * np.exp(-t * (0.5 + 0.35 * i)) / (1 + 0.5 * i)
            for i, r in enumerate([1, 1.52, 2.17, 2.81, 3.4, 4.6]))
    x = x + _bp(_noise(len(t), rng), 800, 5000) * np.exp(-t * 3) * 0.3 * np.clip(t / 0.15, 0, 1)
    return _stereo(_norm(x.astype(np.float32), 0.8), width=0.6)


def fanfare(rng):
    """Short royal trumpet fanfare (C - E - G - C)."""
    notes = [(261.6, 0.0, 0.22), (329.6, 0.24, 0.22), (392.0, 0.48, 0.22), (523.3, 0.72, 1.1)]
    n = int(2.3 * SR)
    out = np.zeros(n, np.float32)
    for f0, at, d in notes:
        t = _t(d)
        f = f0 * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t))
        saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
        tone = _lp(saw.astype(np.float32), 2400) * _env(len(t), 0.03, 0.12, curve=1.3)
        tone2 = _lp((2 * ((np.cumsum(f * 1.5) / SR) % 1) - 1).astype(np.float32), 2000) * _env(len(t), 0.03, 0.12) * 0.35
        _place(out, tone + tone2, at)
    return _stereo(_norm(_reverb(out, 1.6, 0.3, rng)[:n], 0.8), width=0.5)


def coins(rng):
    n = int(1.2 * SR)
    out = np.zeros(n, np.float32)
    for k in range(int(rng.integers(6, 11))):
        t = _t(0.35)
        f = rng.uniform(3500, 6500)
        x = (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 1.48 * t)) * np.exp(-t * rng.uniform(12, 20))
        _place(out, (x * rng.uniform(0.3, 1)).astype(np.float32), rng.uniform(0, 0.7))
    return _stereo(_norm(out, 0.6), width=0.5)


def anvil(rng):
    t = _t(1.6)
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (3 + i)) / (1 + i) for i, f in enumerate([1450, 2160, 3530, 4870]))
    x = x + _hp(_noise(len(t), rng), 1500) * np.exp(-t * 80) * 1.5
    return _stereo(_norm(x.astype(np.float32), 0.75))


def heartbeat(rng, dur=3.0):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    tt = 0.1
    while tt < dur - 0.3:
        for off, g in ((0.0, 1.0), (0.22, 0.7)):
            t = _t(0.15)
            _place(out, (np.sin(2 * np.pi * 50 * t) * _decay(len(t), 25) * g).astype(np.float32), tt + off)
        tt += 0.85
    return _stereo(_norm(_lp(out, 200), 0.9))


def tick(rng, dur=3.0):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    for k in range(int(dur)):
        t = _t(0.03)
        _place(out, (_bp(_noise(len(t), rng), 2000, 6000) * _decay(len(t), 200) * (1 if k % 2 == 0 else 0.7)).astype(np.float32), k + 0.05)
    return _stereo(_norm(out, 0.6))


def creak(rng):
    d = 1.5
    t = _t(d)
    f = 120 + 60 * np.sin(2 * np.pi * 0.7 * t) + 15 * _lp(_noise(len(t), rng), 10)
    pulses = (np.sin(2 * np.pi * np.cumsum(f) / SR) > 0.97).astype(np.float32)
    x = _bp(pulses, 300, 3000) * np.sin(np.pi * t / d)
    return _stereo(_norm(x, 0.6))


def magic_whoosh(rng):
    return _norm(air_soft(rng) * 0.6 + sparkle(rng)[: int(0.85 * SR)] * 0.8, 0.6)


# --------------------------------------------------------------------------- ambience beds (loopable)

def _bed(fn, rng, dur):
    x = fn(rng, dur)
    fade = int(0.8 * SR)
    x[:fade] *= np.linspace(0, 1, fade)[:, None]
    x[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return _loudness(x, 0.08)


def amb_wind(rng, dur):
    t = _t(dur)
    mod = 0.55 + 0.45 * np.sin(2 * np.pi * 0.11 * t + 1) * np.sin(2 * np.pi * 0.047 * t)
    x = _bp(_pink(len(t), rng), 150, 900) * mod
    whistle = _bp(_noise(len(t), rng), 900, 1400) * mod ** 3 * 0.2
    return _stereo((x + whistle).astype(np.float32), width=0.7)


def amb_sea(rng, dur):
    t = _t(dur)
    swell = 0.4 + 0.6 * np.sin(2 * np.pi * t / 7.0) ** 2
    x = _lp(_pink(len(t), rng), 700) * swell + _bp(_noise(len(t), rng), 1500, 6000) * swell ** 5 * 0.25
    return _stereo(x.astype(np.float32), width=0.8)


def amb_rain(rng, dur):
    n = int(dur * SR)
    x = _bp(_pink(n, rng), 800, 9000) * 0.6
    drops = np.zeros(n, np.float32)
    for k in range(int(dur * 25)):
        m = int(0.01 * SR)
        _place(drops, (_hp(_noise(m, rng), 2500) * _decay(m, 300) * rng.uniform(0.1, 0.5)).astype(np.float32), rng.uniform(0, dur))
    return _stereo(x + drops, width=0.8)


def amb_storm(rng, dur):
    out = amb_rain(rng, dur) + amb_wind(rng, dur) * 0.8
    if dur > 6:
        th = thunder(rng) * 0.6
        i = int(rng.uniform(1, dur - 5) * SR)
        out[i:i + len(th)] += th[: len(out) - i]
    return out


def amb_fire(rng, dur):
    n = int(dur * SR)
    x = _lp(_pink(n, rng), 500) * 0.5
    crack = np.zeros(n, np.float32)
    for k in range(int(dur * 9)):
        m = int(rng.uniform(0.004, 0.02) * SR)
        _place(crack, (_hp(_noise(m, rng), 1500) * _decay(m, 220) * rng.uniform(0.15, 1)).astype(np.float32), rng.uniform(0, dur))
    return _stereo(x + crack * 0.7, width=0.5)


def amb_crowd(rng, dur):
    """Murmuring crowd / city."""
    n = int(dur * SR)
    items = []
    for k in range(int(dur * 5)):
        f0 = rng.uniform(110, 260)
        v = voice(rng.uniform(0.25, 0.6), f0 * rng.uniform(0.95, 1.1), f0 * rng.uniform(0.85, 1.05),
                  rng.choice(list(VOWELS)), rng, breath=0.4)
        items.append((v * rng.uniform(0.2, 0.6), rng.uniform(0, dur - 0.6), rng.uniform(-0.9, 0.9)))
    out = _mix_stereo(n, items)
    out = np.stack([_lp(out[:, 0], 2500), _lp(out[:, 1], 2500)], 1)
    return out


def amb_market(rng, dur):
    out = _norm(amb_crowd(rng, dur), 0.7)
    for k in range(int(dur / 2.5)):
        c = coins(rng) * 0.15
        i = int(rng.uniform(0, max(0.1, dur - 1.3)) * SR)
        out[i:i + len(c)] += c[: len(out) - i]
    return out


def amb_battle(rng, dur):
    n = int(dur * SR)
    out = _norm(shout_crowd(rng, dur, 0.8), 0.5)
    for k in range(int(dur * 1.0)):
        c = sword_clash(rng) * rng.uniform(0.2, 0.45)
        i = int(rng.uniform(0, max(0.1, dur - 1.4)) * SR)
        out[i:i + len(c)] += c[: n - i]
    return out


def amb_birds(rng, dur):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    for k in range(int(dur * 1.6)):
        at = rng.uniform(0, dur - 0.5)
        for j in range(int(rng.integers(1, 4))):
            d = rng.uniform(0.06, 0.16)
            t = _t(d)
            f = rng.uniform(2500, 5000) * (1 + rng.uniform(-0.3, 0.3) * t / d)
            _place(out, (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / d) ** 2 * rng.uniform(0.2, 0.6)).astype(np.float32), at + j * 0.14)
    bed = _bp(_pink(n, rng), 200, 1200) * 0.12
    return _stereo(out + bed, width=0.9)


def amb_night(rng, dur):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    t = _t(0.05)
    chirp = np.sin(2 * np.pi * 4300 * t) * np.sin(np.pi * t / 0.05)
    tt = 0.0
    while tt < dur - 0.3:
        for j in range(3):
            _place(out, (chirp * 0.3).astype(np.float32), tt + j * 0.07)
        tt += rng.uniform(0.6, 1.3)
    return _stereo(out + _bp(_pink(n, rng), 100, 600) * 0.08, width=0.8)


def amb_drone(rng, dur):
    t = _t(dur)
    x = sum(np.sin(2 * np.pi * f * t) * 0.3 for f in (55, 82.4, 110.3)) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.07 * t))
    return _stereo(x.astype(np.float32), width=0.3)


# --------------------------------------------------------------------------- registry

ONE_SHOTS = {
    "air_soft": air_soft, "chime_soft": chime_soft, "paper_soft": paper_soft, "pop_soft": pop_soft,
    "slide_soft": slide_soft, "step_soft": step_soft, "sparkle": sparkle, "magic": magic_whoosh,
    "applause": applause, "cheer": cheer, "celebration": celebration, "gasp": gasp_crowd, "laugh": laugh_crowd,
    "scream": scream, "shout": lambda r: _fade(_norm(shout_crowd(r, 2.5), 0.8), 0.05, 0.6), "chaos": chaos,
    "sword_clash": sword_clash, "sword_draw": sword_draw, "war_drums": war_drums, "war_horn": war_horn,
    "arrows": arrows, "battle_burst": battle, "gallop": gallop, "march": march,
    "blast": blast, "explosion": blast, "crash": crash, "thunder": thunder, "rumble": rumble, "earthquake": rumble,
    "fire_burst": fire_burst, "splash": splash, "bell": bell, "gong": gong, "fanfare": fanfare, "trumpet": fanfare,
    "coins": coins, "anvil": anvil, "heartbeat": heartbeat, "tick": tick, "creak": creak,
}
BEDS = {
    "wind": amb_wind, "sea": amb_sea, "waves": amb_sea, "rain": amb_rain, "storm": amb_storm, "fire": amb_fire,
    "crowd": amb_crowd, "city": amb_crowd, "market": amb_market, "battle": amb_battle, "war": amb_battle,
    "birds": amb_birds, "countryside": amb_birds, "forest": amb_birds, "night": amb_night, "drone": amb_drone,
}

# loudness of each sound relative to the sfx bus (dB). Tuned so nothing jumps out over the narration.
LEVELS = {
    "air_soft": -14, "chime_soft": -16, "paper_soft": -14, "pop_soft": -9, "slide_soft": -15, "step_soft": -16,
    "sparkle": -10, "magic": -10,
    "applause": -5, "cheer": -4, "celebration": -4, "gasp": -6, "laugh": -6, "scream": -7, "shout": -6,
    "chaos": -5, "sword_clash": -9, "sword_draw": -8, "war_drums": -5, "war_horn": -6, "arrows": -7,
    "battle_burst": -5, "gallop": -6, "march": -7, "blast": -1, "explosion": -1, "crash": -5, "thunder": -2,
    "rumble": -3, "earthquake": -3, "fire_burst": -5, "splash": -6, "bell": -7, "gong": -6, "fanfare": -6,
    "trumpet": -6, "coins": -9, "anvil": -8, "heartbeat": -4, "tick": -10, "creak": -9,
}

NAMES = sorted(ONE_SHOTS) + sorted(BEDS)


def render(name: str, seed: int = 0, duration: float | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed * 7919 + sum(map(ord, name)))
    if name in BEDS:
        return _bed(BEDS[name], rng, duration or 12.0)
    x = ONE_SHOTS[name](rng)
    if x.ndim == 1:
        x = _stereo(x)
    return _loudness(x)


def _loudness(x: np.ndarray, target_rms: float = 0.12) -> np.ndarray:
    """Even out loudness between sounds (RMS over the loud part), peak capped at 0.95."""
    mono = np.abs(x).mean(axis=1)
    frame = SR // 20
    k = len(mono) // frame
    if k >= 2:
        r = np.sqrt((mono[: k * frame].reshape(k, frame) ** 2).mean(axis=1))
        loud = np.sort(r)[-max(1, k // 3):].mean()
    else:
        loud = float(np.sqrt((mono ** 2).mean()))
    g = target_rms / max(loud, 1e-6)
    g = min(g, 0.95 / max(float(np.abs(x).max()), 1e-6))
    return (x * g).astype(np.float32)
