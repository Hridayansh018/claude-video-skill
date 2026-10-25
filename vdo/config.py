"""Machine settings: tool paths and model files. Read from config.json (optional), .env and environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent      # the vdo-skill folder


@dataclass
class Settings:
    ffmpeg_path: Optional[str] = None
    ffprobe_path: Optional[str] = None
    kokoro_model: str = str(REPO_ROOT / "models" / "kokoro-v1.0.onnx")
    kokoro_voices: str = str(REPO_ROOT / "models" / "voices-v1.0.bin")
    hf_token: Optional[str] = None
    freesound_api_key: Optional[str] = None
    realesrgan_path: Optional[str] = None
    cache_dir: str = str(REPO_ROOT / ".cache")
    sfx_library_dir: str = str(REPO_ROOT / "sfx_library")
    extra: dict = field(default_factory=dict)


def _dotenv(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_settings(config_path: Optional[str] = None) -> Settings:
    s = Settings()
    cfg = Path(config_path) if config_path else REPO_ROOT / "config.json"
    data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    env = _dotenv(REPO_ROOT / ".env")

    def pick(key, env_key):
        return os.environ.get(env_key) or env.get(env_key) or data.get(key) or None

    s.ffmpeg_path = pick("ffmpeg_path", "VDO_FFMPEG")
    s.ffprobe_path = pick("ffprobe_path", "VDO_FFPROBE")
    s.kokoro_model = pick("kokoro_model", "VDO_KOKORO_MODEL") or s.kokoro_model
    s.kokoro_voices = pick("kokoro_voices", "VDO_KOKORO_VOICES") or s.kokoro_voices
    s.hf_token = pick("hf_token", "HF_TOKEN")
    s.freesound_api_key = pick("freesound_api_key", "FREESOUND_API_KEY")
    s.realesrgan_path = pick("realesrgan_path", "REALESRGAN_PATH")
    s.cache_dir = pick("cache_dir", "VDO_CACHE") or s.cache_dir
    s.sfx_library_dir = pick("sfx_library_dir", "VDO_SFX_LIBRARY") or s.sfx_library_dir
    s.extra = {k: v for k, v in data.items() if k not in s.__dataclass_fields__}
    Path(s.cache_dir).mkdir(parents=True, exist_ok=True)
    return s
