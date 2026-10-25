"""Sound effects: your own library first, then Freesound (CC0 / CC-BY only), then
built-in procedural sounds generated from code (no licence needed).

Library layout:   sfx_library/<name>/*.wav|mp3|ogg|flac    e.g. sfx_library/whoosh/whoosh1.wav
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from .util import log, stable_hash, write_json

SR = 48000
AUDIO_EXT = (".wav", ".mp3", ".ogg", ".flac", ".m4a")

# --------------------------------------------------------------------------- procedural


def _noise(n, rng):
    return rng.standard_normal(n).astype(np.float32)


def _lowpass(x, cutoff):
    """One-pole low-pass; cutoff may be an array (sweeps)."""
    cutoff = np.broadcast_to(np.asarray(cutoff, dtype=np.float32), x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # small buffers only; fine for a few seconds of audio
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def _lp(x, cutoff):
    """Low-pass. Fixed cutoff: vectorised FFT (2-pole response, no scipy needed)."""
    if not np.isscalar(cutoff):
        return _lowpass(x, cutoff)
    n = len(x)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    spec *= 1.0 / (1.0 + (f / float(cutoff)) ** 2)
    return np.fft.irfft(spec, n).astype(np.float32)


def _env(n, attack, release, curve=2.0):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((n / SR - t) / max(release, 1e-4), 0, 1) ** curve
    return (a * r).astype(np.float32)


def _stereo(x, pan_sweep=0.0):
    n = len(x)
    if pan_sweep:
        pan = np.linspace(-pan_sweep, pan_sweep, n)
    else:
        pan = np.zeros(n)
    l = x * np.cos((pan + 1) * np.pi / 4)
    r = x * np.sin((pan + 1) * np.pi / 4)
    return np.stack([l, r], axis=1).astype(np.float32)


def _norm(x, peak=0.9):
    m = float(np.max(np.abs(x))) or 1.0
    return x * (peak / m)


def gen_procedural(name: str, seed: int = 0, duration: Optional[float] = None) -> np.ndarray:
    rng = np.random.default_rng(seed + (abs(hash(name)) % 1000))
    if name in ("whoosh", "whoosh_soft", "swish"):
        d = duration or {"whoosh": 0.9, "whoosh_soft": 1.2, "swish": 0.45}[name]
        n = int(d * SR)
        t = np.linspace(0, 1, n)
        sweep = 300 + 3500 * np.sin(np.pi * t) ** 2 if name != "swish" else 800 + 6000 * np.sin(np.pi * t) ** 3
        x = _lowpass(_noise(n, rng), sweep)
        x = x - _lp(x, 120)
        x *= np.sin(np.pi * t) ** (1.5 if name != "whoosh_soft" else 2.5)
        return _stereo(_norm(x, 0.8 if name != "whoosh_soft" else 0.55), pan_sweep=0.7)
    if name in ("impact", "impact_low", "thud"):
        d = duration or 1.4
        n = int(d * SR)
        t = np.arange(n) / SR
        f = 55 * np.exp(-t * 3) + 38 if name != "impact" else 80 * np.exp(-t * 4) + 45
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (4 if name != "thud" else 9))
        crack = _lp(_noise(n, rng), 2500) * np.exp(-t * 30) * (0.9 if name == "impact" else 0.45)
        return _stereo(_norm(body + crack, 0.95))
    if name == "pop":
        n = int((duration or 0.18) * SR)
        t = np.arange(n) / SR
        f = 900 * np.exp(-t * 25) + 300
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)
        return _stereo(_norm(x, 0.7))
    if name == "click":
        n = int(0.05 * SR)
        x = _noise(n, rng) * np.exp(-np.arange(n) / SR * 200)
        return _stereo(_norm(x, 0.5))
    if name == "riser":
        d = duration or 2.5
        n = int(d * SR)
        t = np.linspace(0, 1, n)
        x = _lowpass(_noise(n, rng), 200 + 6000 * t ** 2) * t ** 2
        tone = 0.3 * np.sin(2 * np.pi * np.cumsum(200 + 600 * t ** 2) / SR) * t ** 2
        return _stereo(_norm(x + tone, 0.7))
    if name in ("sword_clash", "metal"):
        n = int((duration or 1.6) * SR)
        t = np.arange(n) / SR
        partials = [1210, 2837, 4122, 5650, 7011]
        x = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * np.exp(-t * (3 + i * 1.5)) / (i + 1)
                for i, f in enumerate(partials))
        x += _lp(_noise(n, rng), 6000) * np.exp(-t * 60) * 2
        return _stereo(_norm(x, 0.8))
    # ---- ambience beds (loopable-ish)
    d = duration or 12.0
    n = int(d * SR)
    t = np.arange(n) / SR
    if name == "wind":
        mod = 0.6 + 0.4 * np.sin(2 * np.pi * 0.11 * t + 1) * np.sin(2 * np.pi * 0.047 * t)
        x = _lp(_noise(n, rng), 500) * mod
    elif name == "sea":
        swell = 0.5 + 0.5 * np.sin(2 * np.pi * t / 6.5) ** 2
        x = _lp(_noise(n, rng), 900) * swell + _lp(_noise(n, rng), 3000) * swell ** 4 * 0.4
    elif name == "fire":
        x = _lp(_noise(n, rng), 700) * 0.5
        crackles = rng.random(n) < 0.0009
        burst = np.zeros(n, dtype=np.float32)
        idx = np.nonzero(crackles)[0]
        for i in idx:
            m = min(n - i, 600)
            burst[i:i + m] += rng.uniform(0.3, 1.0) * np.exp(-np.arange(m) / 60.0) * rng.standard_normal(m)
        x += burst
    elif name in ("crowd", "battle"):
        x = np.zeros(n, dtype=np.float32)
        for k in range(14):  # murmuring voices: band-limited noise with syllable rhythm
            f = rng.uniform(2.5, 5.5)
            syl = (np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) > 0.2).astype(np.float32)
            v = _lp(_noise(n, rng), rng.uniform(600, 1400)) - _lp(_noise(n, rng), 200)
            x += v * _lp(syl, 8) * rng.uniform(0.4, 1.0)
        if name == "battle":
            for _ in range(int(d * 1.2)):
                i = int(rng.uniform(0, n - SR))
                clash = gen_procedural("sword_clash", int(rng.integers(0, 999)))[:, 0] * 0.35
                x[i:i + len(clash)] += clash[: n - i]
    elif name == "rain":
        x = _lp(_noise(n, rng), 5000) - _lp(_noise(n, rng), 400) * 0.5
    elif name == "drone":
        x = sum(np.sin(2 * np.pi * f * t) * 0.3 for f in (55, 82.4, 110.3)) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.07 * t))
    else:
        raise KeyError(name)
    fade = int(0.8 * SR)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    return _stereo(_norm(x.astype(np.float32), 0.6), pan_sweep=0.0)


PROCEDURAL = ["whoosh", "whoosh_soft", "swish", "impact", "impact_low", "thud", "pop", "click", "riser",
              "metal"]   # older built-ins; the main library is sfx_lib (see sfx_lib.NAMES)


def _all_names():
    from . import sfx_lib
    return sorted(set(PROCEDURAL) | set(sfx_lib.ONE_SHOTS)), sorted(sfx_lib.BEDS)


AMBIENCE = {"wind", "sea", "waves", "rain", "storm", "fire", "crowd", "city", "market", "battle", "war", "birds",
            "countryside", "forest", "night", "drone"}


def write_wav(path: str, stereo: np.ndarray) -> None:
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------- resolver

class SFXResolver:
    def __init__(self, library_dir: str, cache_dir: str, freesound_key: Optional[str] = None,
                 use_freesound: bool = False):
        self.library = Path(library_dir)
        self.cache = Path(cache_dir) / "sfx"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.key = freesound_key if use_freesound else None
        self.credits: list[dict] = []
        self._fs_dead = False

    def resolve(self, name: str, seed: int = 0, duration: Optional[float] = None) -> Optional[str]:
        """Return a file path for a named sound, or None if nothing matches."""
        if not name:
            return None
        if os.path.isfile(name):
            return name
        folder = self.library / name
        if folder.is_dir():
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
            if files:
                return str(files[int(stable_hash(name, seed), 16) % len(files)])
        if self.key and not self._fs_dead:
            got = self._freesound(name)
            if got:
                return got
        from . import sfx_lib
        if name in sfx_lib.ONE_SHOTS or name in sfx_lib.BEDS:
            bed = name in sfx_lib.BEDS
            dur_key = round(duration, 1) if (duration and bed) else None
            out = self.cache / f"lib2_{name}_{seed % 4}_{dur_key}.wav"
            if not out.exists():
                write_wav(str(out), sfx_lib.render(name, seed % 4, duration if bed else None))
            return str(out)
        if name in PROCEDURAL:
            dur_key = round(duration, 1) if (duration and name in AMBIENCE) else None
            out = self.cache / f"proc_{name}_{seed % 4}_{dur_key}.wav"
            if not out.exists():
                write_wav(str(out), gen_procedural(name, seed % 4, duration if name in AMBIENCE else None))
            return str(out)
        log(f"    sfx '{name}' not found in library, Freesound or built-ins; skipped")
        return None

    def _freesound(self, query: str) -> Optional[str]:
        folder = self.cache / "freesound" / query
        if folder.is_dir():
            files = sorted(folder.glob("*.mp3"))
            if files:
                return str(files[0])
        params = {
            "query": query.replace("_", " "),
            "filter": 'license:("Creative Commons 0" OR "Attribution") duration:[0.2 TO 30]',
            "fields": "id,name,username,license,url,previews,duration",
            "sort": "rating_desc", "page_size": "5", "token": self.key,
        }
        url = "https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            results = data.get("results") or []
            if not results:
                return None
            best = results[0]
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / f"{best['id']}.mp3"
            preview = best["previews"].get("preview-hq-mp3") or best["previews"].get("preview-lq-mp3")
            urllib.request.urlretrieve(preview, dest)
            credit = {"name": best["name"], "author": best["username"], "license": best["license"],
                      "url": best["url"], "file": str(dest)}
            write_json(str(dest) + ".json", credit)
            self.credits.append(credit)
            return str(dest)
        except Exception as e:
            log(f"    Freesound lookup failed for '{query}' ({e}); using built-ins")
            self._fs_dead = True
            return None

    def credit_for(self, path: str) -> Optional[dict]:
        meta = path + ".json"
        if os.path.exists(meta):
            with open(meta, encoding="utf-8") as f:
                return json.load(f)
        return None
