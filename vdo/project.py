"""Project file: load, validate and fill defaults.

A project is plain JSON (see examples/ and README). Everything a video needs is
data here: script lines, styles, durations, images, overlays, sound.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Optional

from .util import read_json

DEFAULTS: dict[str, Any] = {
    "name": "Untitled",
    "output_dir": None,                  # default: <project dir>/output
    "canvas": {"width": 1920, "height": 1080, "fps": 30},
    "voice": {"provider": "kokoro", "voice": "bm_george", "speed": 1.0, "lang": "en-gb",
              "edge_voice": "en-US-ChristopherNeural", "rate": "+0%", "pitch": "+0Hz"},
    "default_style": "stickman",
    "image_duration": 6.0,               # preferred seconds per image (T)
    "max_images_per_scene": 3,           # cap on images per scene; extra cuts reuse them as crops
    "image_provider": None,              # override every style's generator provider (hf_flux | placeholder)
    "timing": {
        "duration_mode": "script",       # script: use scene "duration" when given | voice: follow voiceover
        "scene_padding": 0.35,           # silence after the voiceover inside a scene
        "voice_offset": 0.15,            # voiceover starts this long after the scene starts
        "snap_window": 0.6,              # move cuts up to this far to land between words
        "min_cut": 1.0,                  # absolute minimum on-screen time
    },
    "style_change": {"type": "fadewhite", "duration": 0.7},
    "style_overrides": {},
    "subtitles": {"enabled": True, "burn_in": False, "max_words": 7, "max_chars": 42},
    "audio": {
        "music": "auto", "music_gain_db": -21.0, "duck_db": -10.0,
        "voice_gain_db": 0.0, "sfx_gain_db": -9.0, "ambience_gain_db": -26.0,
        "target_lufs": -14.0, "auto_sfx": True, "freesound": False,
    },
    "outputs": ["ffmpeg"],
    "render": {"crf": 16, "preset": "veryfast", "final_crf": 18, "final_preset": "medium",
               "motion_blur_samples": 8, "shutter": 180, "workers": None, "quality": "normal"},
    "seed": 0,
    "scenes": [],
}

SCENE_DEFAULTS: dict[str, Any] = {
    "id": None,
    "voiceover": "",
    "style": None,
    "duration": None,
    "image_duration": None,
    "images": None,
    "visual": None,
    "image_count": None,
    "continue": False,
    "transition_in": None,
    "motion": None,
    "sfx": [],
    "ambience": None,
    "overlay": None,
    "title": None,
    "clip": None,        # optional animated clip (e.g. a Google Flow / Veo video) used instead of stills
    "clip_volume_db": -14.0,
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class ProjectError(ValueError):
    pass


def normalize(data: dict, base_dir: str, style_names: list[str]) -> dict:
    p = _merge(DEFAULTS, data)
    p["base_dir"] = str(Path(base_dir).resolve())
    if not p.get("output_dir"):
        p["output_dir"] = str(Path(base_dir) / "output")
    elif not os.path.isabs(p["output_dir"]):
        p["output_dir"] = str((Path(base_dir) / p["output_dir"]).resolve())

    if p["default_style"] not in style_names:
        raise ProjectError(f"default_style '{p['default_style']}' is not a known style ({', '.join(style_names)})")
    if not p["scenes"]:
        raise ProjectError("Project has no scenes.")
    if p["image_duration"] <= 0:
        raise ProjectError("image_duration must be > 0")

    seen = set()
    scenes = []
    for i, raw in enumerate(p["scenes"]):
        if isinstance(raw, str):
            raw = {"voiceover": raw}
        sc = _merge(SCENE_DEFAULTS, raw)
        sc["index"] = i
        sc["id"] = str(sc["id"] or f"s{i + 1:02d}")
        if sc["id"] in seen:
            raise ProjectError(f"Duplicate scene id '{sc['id']}'")
        seen.add(sc["id"])
        sc["style"] = sc["style"] or p["default_style"]
        if sc["style"] not in style_names:
            raise ProjectError(f"Scene {sc['id']}: unknown style '{sc['style']}'")
        if sc["duration"] is not None and float(sc["duration"]) <= 0:
            raise ProjectError(f"Scene {sc['id']}: duration must be > 0")
        if not sc["voiceover"] and sc["duration"] is None:
            raise ProjectError(f"Scene {sc['id']}: needs a voiceover or a duration")
        if sc.get("clip"):
            sc["clip"] = _abs(sc["clip"], base_dir)
        if sc["images"] is not None:
            sc["images"] = [_norm_image(x, base_dir) for x in sc["images"]]
        if sc["overlay"]:
            sc["overlay"] = _norm_overlay(sc["overlay"], base_dir, sc["id"])
        if i == 0 and sc["continue"]:
            raise ProjectError("The first scene cannot 'continue' a previous scene.")
        if not sc["continue"] and not sc["images"] and not sc["visual"] and not sc["overlay"]:
            # fall back to the voiceover text as the picture description
            sc["visual"] = sc["voiceover"]
        sc["sfx"] = [_norm_sfx(x) for x in (sc["sfx"] or [])]
        scenes.append(sc)
    p["scenes"] = scenes
    if p["audio"].get("music") and p["audio"]["music"] != "auto":
        p["audio"]["music"] = _abs(p["audio"]["music"], base_dir)
    return p


def _abs(path: str, base_dir: str) -> str:
    return path if os.path.isabs(path) else str((Path(base_dir) / path).resolve())


def _norm_image(x, base_dir: str) -> dict:
    if isinstance(x, str):
        looks_like_file = os.path.splitext(x)[1].lower() in (".png", ".jpg", ".jpeg", ".webp")
        x = {"path": x} if looks_like_file else {"prompt": x}
    x = dict(x)
    if x.get("path"):
        x["path"] = _abs(x["path"], base_dir)
    elif not x.get("prompt"):
        raise ProjectError(f"Image entry needs 'prompt' or 'path': {x}")
    return x


def _norm_sfx(x) -> dict:
    if isinstance(x, str):
        return {"name": x, "at": None}
    x = dict(x)
    if "name" not in x and "path" not in x:
        raise ProjectError(f"SFX entry needs 'name' or 'path': {x}")
    return x


def _norm_overlay(ov: dict, base_dir: str, sid: str) -> dict:
    ov = dict(ov)
    if ov.get("background"):
        ov["background"] = _norm_image(ov["background"], base_dir)
    layers = []
    for j, layer in enumerate(ov.get("layers", [])):
        layer = dict(layer)
        layer.setdefault("id", f"layer{j + 1}")
        layer.setdefault("kind", "character")
        if not layer.get("image"):
            raise ProjectError(f"Scene {sid}: overlay layer '{layer['id']}' needs an 'image'")
        layer["image"] = _norm_image(layer["image"], base_dir)
        poses = []
        for pose in layer.get("poses", []):
            pose = dict(pose)
            pose["image"] = _norm_image(pose["image"], base_dir)
            poses.append(pose)
        layer["poses"] = sorted(poses, key=lambda q: q["t"])
        kfs = layer.get("keyframes") or []
        if not kfs and not layer.get("popup"):
            raise ProjectError(f"Scene {sid}: overlay layer '{layer['id']}' needs 'keyframes' or a 'popup'")
        layer["keyframes"] = sorted(kfs, key=lambda k: k["t"])
        layer.setdefault("height", 0.6 if layer["kind"] == "character" else 0.3)
        layer.setdefault("motion_blur", True)
        layer.setdefault("shadow", True)
        layers.append(layer)
    ov["layers"] = layers
    ov.setdefault("fx", [])
    ov.setdefault("background_motion", "push_in")
    return ov


def safe_name(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in s.strip())
    return keep.strip("_") or "project"


def load_project(path: str, style_names: list[str]) -> dict:
    data = read_json(path)
    return normalize(data, str(Path(path).resolve().parent), style_names)
