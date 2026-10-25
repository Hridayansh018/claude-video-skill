"""Shared helpers: hashing, easing, ffmpeg discovery and execution."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

# --------------------------------------------------------------------------- hashing


def stable_hash(*parts, length: int = 16) -> str:
    """Deterministic short hash of any JSON-serialisable parts."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:length]


def file_hash(path: str | os.PathLike, length: int = 16) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:length]


# --------------------------------------------------------------------------- easing

def _ease_in_out_sine(t): return -(math.cos(math.pi * t) - 1) / 2


def _ease_out_back(t, s=1.70158):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def _ease_out_elastic(t):
    if t in (0, 1):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


def _ease_out_bounce(t):
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


EASINGS = {
    "linear": lambda t: t,
    "easeInQuad": lambda t: t * t,
    "easeOutQuad": lambda t: 1 - (1 - t) ** 2,
    "easeInOutQuad": lambda t: 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2,
    "easeInCubic": lambda t: t ** 3,
    "easeOutCubic": lambda t: 1 - (1 - t) ** 3,
    "easeInOutCubic": lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
    "easeOutQuint": lambda t: 1 - (1 - t) ** 5,
    "easeInOutSine": _ease_in_out_sine,
    "easeOutExpo": lambda t: 1 if t >= 1 else 1 - 2 ** (-10 * t),
    "easeInExpo": lambda t: 0 if t <= 0 else 2 ** (10 * t - 10),
    "easeOutBack": _ease_out_back,
    "easeOutElastic": _ease_out_elastic,
    "easeOutBounce": _ease_out_bounce,
    "hold": lambda t: 0.0 if t < 1 else 1.0,
}


def ease(name: Optional[str], t: float) -> float:
    t = min(1.0, max(0.0, t))
    fn = EASINGS.get(name or "easeInOutCubic")
    if fn is None:
        raise ValueError(f"Unknown easing '{name}'. Options: {', '.join(EASINGS)}")
    return fn(t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# --------------------------------------------------------------------------- ffmpeg

def _venv_bin(name: str) -> list[Path]:
    exe = name + (".exe" if os.name == "nt" else "")
    roots = [Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")]
    return [r / exe for r in roots]


def find_binary(name: str, configured: Optional[str] = None) -> str:
    """Find ffmpeg/ffprobe: config value -> env var -> PATH -> active venv -> imageio-ffmpeg."""
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    env = os.environ.get(f"VIDEOENGINE_{name.upper()}")
    if env:
        candidates.append(env)
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    found = shutil.which(name)
    if found:
        return found
    for p in _venv_bin(name):
        if p.exists():
            return str(p)
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg  # type: ignore
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    raise FileNotFoundError(
        f"Could not find '{name}'. Install it, add it to PATH, or set '{name}_path' in config.json."
    )


class FFmpeg:
    """Tiny wrapper around ffmpeg/ffprobe binaries."""

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        self.ffmpeg = find_binary("ffmpeg", ffmpeg_path)
        try:
            self.ffprobe = find_binary("ffprobe", ffprobe_path)
        except FileNotFoundError:
            self.ffprobe = None  # duration falls back to ffmpeg parsing

    def run(self, args: Sequence[str], cwd: Optional[str] = None, quiet: bool = True) -> None:
        cmd = [self.ffmpeg, "-hide_banner", "-y"] + (["-loglevel", "error"] if quiet else []) + list(args)
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-3000:]
            raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{' '.join(cmd)[:1500]}\n---\n{tail}")

    def duration(self, path: str) -> float:
        if self.ffprobe:
            out = subprocess.run(
                [self.ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                capture_output=True, text=True,
            )
            try:
                return float(json.loads(out.stdout)["format"]["duration"])
            except Exception:
                pass
        proc = subprocess.run([self.ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        for line in proc.stderr.splitlines():
            line = line.strip()
            if line.startswith("Duration:"):
                h, m, s = line.split(",")[0].split()[1].split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
        raise RuntimeError(f"Could not read duration of {path}")

    def decode_audio(self, path: str, sr: int = 48000):
        """Decode any audio file to a float32 stereo numpy array (n, 2)."""
        import numpy as np
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path,
               "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Could not decode audio {path}: {proc.stderr.decode(errors='replace')[-500:]}")
        data = np.frombuffer(proc.stdout, dtype=np.float32)
        return data.reshape(-1, 2).copy()


def write_json(path: str | os.PathLike, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_json(path: str | os.PathLike):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode(), flush=True)


def chunks(seq: Iterable, n: int):
    buf = []
    for x in seq:
        buf.append(x)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf
