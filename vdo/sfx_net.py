"""Real recorded sound effects from SFXMint (https://sfxmint.com): CC0 / public domain, free, no account,
no API key. A starter pack of the sounds below ships in sfx_library/_sfxmint/ so the engine works offline;
anything missing is downloaded once from https://sfxmint.com/dl/<slug>.mp3 and kept there.

Each sound name used by the engine maps to a few curated SFXMint sounds (picked by hand, several to
vary the choice). Anything not listed here (or when SFXMint cannot be reached) falls back to the
sounds generated in code (sfx_lib.py).

Set  "audio": {"sfx_source": "builtin"}  in project.json to use only the generated sounds.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

SR = 48000
BASE = "https://sfxmint.com/dl/"

# engine sound name -> SFXMint slugs (first is the default, the others are alternates)
ONE_SHOTS: dict[str, list[str]] = {
    "blast": ["impact-explosion-02", "impact-explosion-09"],
    "explosion": ["impact-explosion-02", "impact-explosion-09"],
    "thunder": ["ambience-thunder-06", "lightning-strike-03"],
    "earthquake": ["earthquake-falling-stones-01"],
    "rumble": ["earthquake-falling-stones-01"],
    "crash": ["impact-crash-36", "rock-crumbling-03"],
    "applause": ["crowd-applause-01"],
    "cheer": ["crowd-cheer-43", "crowd-cheer-44"],
    "celebration": ["crowd-cheer-44", "crowd-applause-01"],
    "scream": ["human-scream-05"],
    "gasp": ["crowd-gasp-43"],
    "laugh": ["laugh-03"],
    "sword_clash": ["sword-clash-01", "sword-clash-02"],
    "battle_burst": ["sword-clash-02", "sword-clash-01"],
    "sword_draw": ["impact-sword-draw-02"],
    "arrows": ["arrow-flyby-01", "impact-bow-08"],
    "gallop": ["animal-horse-gallop-07"],
    "war_drums": ["timpani-strike-01", "acoustic-drum-kit-floor-tom-01"],
    "drum_hit": ["timpani-strike-01", "acoustic-drum-kit-floor-tom-01"],
    "fanfare": ["trumpet-fanfare-04", "trumpet-fanfare-05"],
    "trumpet": ["trumpet-fanfare-05", "trumpet-fanfare-04"],
    "bell": ["instrument-bell-36"],
    "gong": ["instrument-gong-36"],
    "coins": ["coins-handled-by-hand-02"],
    "heartbeat": ["horror-heartbeat-34"],
    "creak": ["door-creak-05"],
    "anvil": ["impact-metal-hit-32"],
    "hit": ["transition-impact-hit-36", "short-video-impact-01"],
    "braam": ["transition-braam-28"],
    "riser": ["transition-riser-01"],
    "drop": ["bass-drop-03", "downlifter-02"],
}

# ambience beds (looped by the engine; made seamless here)
BEDS: dict[str, list[str]] = {
    "fire": ["ambience-fireplace-50", "gentle-fire-crackling-01"],
    "wind": ["ambience-wind-31", "ambience-wind-09"],
    "rain": ["ambience-rain-05"],
    "storm": ["ambience-rain-05"],
    "sea": ["ambience-ocean-54"],
    "waves": ["ambience-ocean-54"],
    "countryside": ["park-bird-ambience-01"],
    "birds": ["park-bird-ambience-01"],
    "cave": ["cave-ambience-01"],
    "drone": ["tension-drone-01"],
    "tension": ["tension-drone-01"],
}

NAMES = sorted(set(ONE_SHOTS) | set(BEDS))


def has(name: str) -> bool:
    return name in ONE_SHOTS or name in BEDS


def _local(pack_dir: Path, slug: str, online: bool) -> Optional[Path]:
    for ext in (".mp3", ".wav"):
        p = pack_dir / f"{slug}{ext}"
        if p.exists() and p.stat().st_size > 1000:
            return p
    if not online:
        return None
    pack_dir.mkdir(parents=True, exist_ok=True)
    dest = pack_dir / f"{slug}.mp3"
    try:
        req = urllib.request.Request(BASE + slug + ".mp3", headers={"User-Agent": "claude-video-skill"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) < 1000:
            return None
        dest.write_bytes(data)
        return dest
    except Exception:
        return None


def _load(path: Path) -> Optional[np.ndarray]:
    try:
        import soundfile as sf
        x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        return None
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if sr != SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(SR, sr)
        x = resample_poly(x, SR // g, sr // g, axis=0).astype(np.float32)
    return x


def _seamless(x: np.ndarray, fade_s: float = 1.2) -> np.ndarray:
    """Make a recording loop without a click: cross-fade its tail into its start."""
    n = len(x)
    f = int(min(fade_s * SR, n // 3))
    if f < 100:
        return x
    head, tail = x[:f], x[n - f:]
    w = np.linspace(0, 1, f, dtype=np.float32)[:, None]
    blend = tail * (1 - w) + head * w
    return np.concatenate([x[f: n - f], blend], axis=0).astype(np.float32)


def get(name: str, library_dir: str, cache_dir: Path, seed: int = 0, online: bool = True) -> Optional[str]:
    """Path of a level-matched 48 kHz wav for `name`, or None (then the caller uses the built-ins)."""
    table = BEDS if name in BEDS else ONE_SHOTS if name in ONE_SHOTS else None
    if table is None:
        return None
    slugs = table[name]
    slug = slugs[seed % len(slugs)]
    out = cache_dir / f"sfxmint_{slug}.wav"
    if out.exists():
        return str(out)
    src = _local(Path(library_dir) / "_sfxmint", slug, online)
    if src is None:
        return None
    x = _load(src)
    if x is None or len(x) < 100:
        return None
    from .sfx_lib import _loudness
    bed = name in BEDS
    if bed:
        x = _seamless(x)
    # trim leading digital silence of one-shots so the hit lands on the cue
    if not bed:
        lead = np.abs(x).max(axis=1)
        idx = np.argmax(lead > 0.02 * max(lead.max(), 1e-6))
        x = x[max(0, idx - int(0.01 * SR)):]
    x = _loudness(x, 0.08 if bed else 0.12)
    import soundfile as sf
    cache_dir.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), x, SR, subtype="PCM_16")
    return str(out)


def prefetch(library_dir: str) -> tuple[int, int]:
    """Download every curated sound that is not in the pack yet. Returns (have, wanted)."""
    slugs = sorted({s for t in (ONE_SHOTS, BEDS) for v in t.values() for s in v})
    have = sum(1 for s in slugs if _local(Path(library_dir) / "_sfxmint", s, True))
    return have, len(slugs)
