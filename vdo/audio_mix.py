"""Mix voiceover, sound effects, ambience beds and music into one track.

Mixing happens in numpy (48 kHz stereo): each clip is decoded once and placed at its time.
Music is ducked under the voice; the result is loudness-normalised by ffmpeg at the end.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .sfx import write_wav

SR = 48000


def db(x: float) -> float:
    return 10 ** (x / 20.0)


class Mixer:
    def __init__(self, duration: float, ff):
        self.n = int(np.ceil(duration * SR)) + SR // 2
        self.buses = {name: np.zeros((self.n, 2), dtype=np.float32) for name in ("voice", "sfx", "amb", "music")}
        self.ff = ff
        self._decoded: dict[str, np.ndarray] = {}
        self.events: list[dict] = []   # for timeline exports

    def _load(self, path: str) -> np.ndarray:
        if path not in self._decoded:
            self._decoded[path] = self.ff.decode_audio(path, SR)
        return self._decoded[path]

    def place(self, bus: str, path: str, at: float, gain_db: float = 0.0, length: Optional[float] = None,
              loop: bool = False, fade_in: float = 0.01, fade_out: float = 0.05, label: str = "") -> None:
        clip = self._load(path)
        if length is not None:
            want = int(length * SR)
            if loop and len(clip) < want:
                reps = int(np.ceil(want / max(1, len(clip))))
                clip = np.tile(clip, (reps, 1))
            clip = clip[:want]
        clip = clip * db(gain_db)
        fi, fo = int(fade_in * SR), int(fade_out * SR)
        clip = clip.copy()
        fi = min(fi, len(clip))
        if fi > 0:
            clip[:fi] *= np.linspace(0, 1, fi)[:, None]
        if fo > 0 and len(clip) > fo:
            clip[-fo:] *= np.linspace(1, 0, fo)[:, None]
        start = int(max(0.0, at) * SR)
        end = min(self.n, start + len(clip))
        if end > start:
            self.buses[bus][start:end] += clip[: end - start]
        self.events.append({"bus": bus, "path": path, "at": round(at, 3), "gain_db": gain_db,
                            "length": round((end - start) / SR, 3), "label": label})

    def render(self, out_wav: str, duck_db: float = -10.0) -> str:
        voice = self.buses["voice"]
        music = self.buses["music"]
        amb = self.buses["amb"]
        if np.any(music) or np.any(amb):
            # side-chain: smooth voice envelope -> gain reduction on music (and a little on ambience)
            env = np.abs(voice).max(axis=1)
            win = int(0.25 * SR)
            kernel = np.ones(win, dtype=np.float32) / win
            env = np.convolve(env, kernel, mode="same")
            amount = np.clip(env / 0.05, 0, 1)
            music = music * (1 - (1 - db(duck_db)) * amount)[:, None]
            amb = amb * (1 - (1 - db(-4.0)) * amount)[:, None]
        # soft limiter on effects so a blast cannot punch through the narration
        sfx = self.buses["sfx"]
        sfx = np.where(np.abs(sfx) > 0.5, np.sign(sfx) * (0.5 + 0.5 * np.tanh((np.abs(sfx) - 0.5) / 0.5)), sfx)
        mix = voice + sfx + amb + music
        peak = float(np.max(np.abs(mix))) or 1.0
        self.headroom = 0.98 / peak if peak > 0.98 else 1.0
        mix = mix * self.headroom
        self._music_ducked = music
        write_wav(out_wav, mix)
        return out_wav

    def write_stems(self, folder: str) -> dict:
        """Write each bus (already at its mix level) as a full-length WAV for editors."""
        import os
        os.makedirs(folder, exist_ok=True)
        out = {}
        for name in ("voice", "sfx", "amb", "music"):
            data = self._music_ducked if name == "music" else self.buses[name]
            if not np.any(data):
                continue
            path = os.path.join(folder, f"stem_{name}.wav")
            write_wav(path, data * getattr(self, "headroom", 1.0))
            out[name] = path
        return out
