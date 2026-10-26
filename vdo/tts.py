"""Voiceover generation with word timings.

Providers:
  kokoro - Kokoro open-source voice model, fully offline (default; needs the two model files in models/)
  edge   - Microsoft Edge neural voices via edge-tts (free, needs internet)
  dummy  - offline stand-in: soft tone per word with estimated timings (for testing)
  file   - use a recorded file: scene {"voice_file": "path.mp3"} (timings estimated)
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import wave
from pathlib import Path
from typing import Optional

from .util import FFmpeg, read_json, stable_hash, write_json, log

TICKS = 10_000_000  # edge-tts offsets are in 100 ns units


def _words_estimate(text: str, total: Optional[float] = None, wpm: float = 150.0) -> list[dict]:
    tokens = re.findall(r"\S+", text)
    if not tokens:
        return []
    weights = []
    for tok in tokens:
        w = 0.18 + 0.055 * len(re.sub(r"\W", "", tok))
        if tok.endswith((",", ";", ":")):
            w += 0.18
        if tok.endswith((".", "!", "?")):
            w += 0.35
        weights.append(w)
    scale = 1.0
    natural = sum(weights)
    if total:
        scale = total / natural
    else:
        scale = (len(tokens) / (wpm / 60.0)) / natural
    t = 0.0
    out = []
    for tok, w in zip(tokens, weights):
        d = w * scale
        speak = d * 0.82
        out.append({"text": tok, "start": round(t, 3), "end": round(t + speak, 3)})
        t += d
    return out


def _write_dummy_wav(path: str, words: list[dict], total: float, sr: int = 48000) -> None:
    import numpy as np
    n = int(math.ceil(total * sr))
    buf = np.zeros(n, dtype=np.float32)
    for i, w in enumerate(words):
        a, b = int(w["start"] * sr), int(w["end"] * sr)
        if b <= a:
            continue
        t = np.arange(b - a) / sr
        f0 = 140 + 25 * math.sin(i * 1.7)
        tone = 0.25 * np.sin(2 * np.pi * f0 * t) + 0.08 * np.sin(2 * np.pi * 2 * f0 * t)
        env = np.minimum(1.0, np.minimum(t / 0.02, (t[-1] - t + 1e-3) / 0.04))
        buf[a:b] += (tone * env).astype(np.float32)
    pcm = (np.clip(buf, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


_KOKORO = {}


def _split_sentences(text: str) -> list[str]:
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    parts = re.split(r'(?<=[.!?])["\u201d\u2019]?\s+(?=[A-Z"\u201c])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _voice_lang(voice: str) -> str:
    from .voices import lang_for
    return lang_for(voice)


def _kokoro_synth(text: str, cfg: dict, settings, out_path: str):
    """Voice sentence by sentence so every sentence has an exact start time; words are spread inside it."""
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro
    key = (settings.kokoro_model, settings.kokoro_voices)
    if key not in _KOKORO:
        if not (os.path.exists(key[0]) and os.path.exists(key[1])):
            raise RuntimeError(f"Kokoro model files not found ({key[0]}, {key[1]}). See INSTALL.md step 4.")
        _KOKORO[key] = Kokoro(*key)
    k = _KOKORO[key]
    gap = float(cfg.get("sentence_gap", 0.28))
    audio, words, t, sr = [], [], 0.0, 24000
    for s in _split_sentences(text):
        a, sr = k.create(s, voice=cfg.get("voice", "bm_george"), speed=float(cfg.get("speed", 1.0)),
                         lang=cfg.get("lang") or _voice_lang(cfg.get("voice", "bm_george")))
        a = np.asarray(a, dtype=np.float32)
        nz = np.nonzero(np.abs(a) > 0.01)[0]
        if len(nz):
            a = a[max(0, nz[0] - 240): nz[-1] + 1200]
        dur = len(a) / sr
        for w in _words_estimate(s, dur):
            words.append({"text": w["text"], "start": round(t + w["start"], 3), "end": round(t + w["end"], 3)})
        audio += [a, np.zeros(int(gap * sr), np.float32)]
        t += dur + gap
    full = np.concatenate(audio[:-1]) if audio else np.zeros(sr, np.float32)
    sf.write(out_path, full, sr)
    return words, len(full) / sr


async def _edge_synth(text: str, voice: str, rate: str, pitch: str, out_path: str) -> list[dict]:
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:  # edge-tts < 7 always sends word boundaries
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    words = []
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                st = chunk["offset"] / TICKS
                words.append({"text": chunk["text"], "start": round(st, 3),
                              "end": round(st + chunk["duration"] / TICKS, 3)})
    return words


def synthesize(scene: dict, voice_cfg: dict, out_dir: str, ff: FFmpeg, settings=None) -> dict:
    """Return {'path', 'duration', 'words'} for the scene's voiceover (or None if silent)."""
    text = (scene.get("voiceover") or "").strip()
    if not text and not scene.get("voice_file"):
        return None
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    provider = voice_cfg.get("provider", "edge")
    if scene.get("voice_file"):
        provider = "file"
    key = stable_hash(provider, text, voice_cfg.get("voice"), voice_cfg.get("rate"), voice_cfg.get("pitch"),
                      scene.get("voice_file"))
    key = stable_hash(provider, text, voice_cfg.get("voice"), voice_cfg.get("speed"), voice_cfg.get("rate"),
                      voice_cfg.get("pitch"), voice_cfg.get("edge_voice"), scene.get("voice_file"))
    ext = "mp3" if provider == "edge" else "wav"
    audio = os.path.join(out_dir, f"{scene['id']}_{key}.{ext}")
    meta = audio + ".json"
    if os.path.exists(audio) and os.path.exists(meta) and os.path.getsize(audio) > 500:
        return read_json(meta)

    if provider == "kokoro":
        words, dur = _kokoro_synth(text, voice_cfg, settings, audio)
    elif provider == "edge":
        try:
            words = asyncio.run(_edge_synth(text, voice_cfg.get("edge_voice", "en-US-ChristopherNeural"),
                                            voice_cfg.get("rate", "+0%"), voice_cfg.get("pitch", "+0Hz"), audio))
        except Exception as e:
            raise RuntimeError(
                f"edge-tts failed for scene {scene['id']} ({e}). Check your internet connection, or set "
                f"\"voice\": {{\"provider\": \"dummy\"}} to test offline."
            ) from e
        dur = ff.duration(audio)
        if not words:
            words = _words_estimate(text, dur)
    elif provider == "file":
        src = scene["voice_file"]
        ff.run(["-i", src, "-ac", "1", "-ar", "48000", audio])
        dur = ff.duration(audio)
        words = _words_estimate(text, dur) if text else []
    elif provider == "dummy":
        words = _words_estimate(text)
        dur = (words[-1]["end"] + 0.25) if words else 1.0
        _write_dummy_wav(audio, words, dur)
    else:
        raise ValueError(f"Unknown voice provider '{provider}' (kokoro, edge, dummy)")

    result = {"path": audio, "duration": round(dur, 3), "words": words, "provider": provider}
    write_json(meta, result)
    log(f"  voice {scene['id']}: {dur:.2f}s, {len(words)} words ({provider})")
    return result
