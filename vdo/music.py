"""A gentle storybook music bed generated in code (no licence needed): soft pad chords,
a plucked arpeggio and a glockenspiel accent, looped to the video's length."""

import math

import numpy as np

SR = 48000

PROGRESSIONS = {
    "warm": [(62, 66, 69), (57, 61, 64), (59, 62, 66), (55, 59, 62)],      # D A Bm G
    "wonder": [(60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62)],    # C Am F G
    "serious": [(57, 60, 64), (53, 57, 60), (60, 64, 67), (55, 59, 62)],   # Am F C G
}


def music_bed(total: float, mood: str = "warm", bpm: int = 84) -> np.ndarray:
    prog = PROGRESSIONS.get(mood, PROGRESSIONS["warm"])
    beat = 60 / bpm
    bar = beat * 4
    loop_len = bar * len(prog)
    n = int(loop_len * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    f = lambda m: 440 * 2 ** ((m - 69) / 12)
    for bi, ch in enumerate(prog):
        s0, s1 = int(bi * bar * SR), int((bi + 1) * bar * SR)
        tt = t[: s1 - s0]
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.5)
        for m in ch:
            fr = f(m - 12)
            out[s0:s1] += (np.sin(2 * np.pi * fr * tt) * 0.5 + np.sin(2 * np.pi * fr * 2 * tt) * 0.12) * env * 0.12
        arp = [ch[0], ch[1], ch[2], ch[1] + 12, ch[2], ch[1], ch[0] + 12, ch[2]]
        for k, m in enumerate(arp):
            a0 = s0 + int(k * beat / 2 * SR)
            L = int(0.9 * SR)
            tp = np.arange(L) / SR
            fr = f(m)
            pl = (np.sin(2 * np.pi * fr * tp) + 0.3 * np.sin(2 * np.pi * 2 * fr * tp)) * np.exp(-tp * 5.5) * 0.09
            e = min(n, a0 + L)
            out[a0:e] += pl[: e - a0]
        L = int(1.6 * SR)
        tp = np.arange(L) / SR
        fr = f(ch[2] + 24)
        gl = (np.sin(2 * np.pi * fr * tp) + 0.25 * np.sin(2 * np.pi * 2.76 * fr * tp)) * np.exp(-tp * 3) * 0.05
        e = min(n, s0 + L)
        out[s0:e] += gl[: e - s0]
    reps = int(math.ceil(total / loop_len)) + 1
    full = np.tile(out, reps)[: int(total * SR)]
    fade = int(min(3.0, total / 4) * SR)
    if fade:
        full[:fade] *= np.linspace(0, 1, fade)
        full[-fade:] *= np.linspace(1, 0, fade)
    return np.stack([full, full], 1).astype(np.float32)
