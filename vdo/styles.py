"""Style presets: load styles.json, merge project overrides, build prompts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

from .util import read_json

XFADE_TYPES = {
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "rectcrop", "distance", "fadeblack", "fadewhite", "radial", "smoothleft", "smoothright",
    "smoothup", "smoothdown", "circleopen", "circleclose", "vertopen", "vertclose", "horzopen", "horzclose",
    "dissolve", "pixelize", "diagtl", "diagtr", "diagbl", "diagbr", "hlslice", "hrslice", "vuslice", "vdslice",
    "hblur", "fadegrays", "wipetl", "wipetr", "wipebl", "wipebr", "squeezeh", "squeezev", "zoomin",
    "fadefast", "fadeslow", "cut",
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class StyleBook:
    def __init__(self, styles: dict):
        self.styles = {k: v for k, v in styles.items() if not k.startswith("_")}
        for name, st in self.styles.items():
            for kind in ("cut", "scene"):
                t = st.get("transitions", {}).get(kind, {}).get("type", "cut")
                if t not in XFADE_TYPES:
                    raise ValueError(f"Style '{name}': unknown transition type '{t}'")

    @classmethod
    def load(cls, path: Optional[str] = None, overrides: Optional[dict] = None) -> "StyleBook":
        base = read_json(path or Path(__file__).resolve().parent / "styles.json")
        merged = dict(base)
        for name, over in (overrides or {}).items():
            merged[name] = _deep_merge(base.get(name, {}), over) if name in base else over
        return cls(merged)

    def get(self, name: str) -> dict:
        if name not in self.styles:
            raise KeyError(f"Unknown style '{name}'. Available: {', '.join(self.styles)}")
        return self.styles[name]

    def names(self):
        return list(self.styles)

    # ---------------------------------------------------------------- prompts
    def scene_prompt(self, style: str, subject: str, shot: Optional[str] = None, extra: str = "") -> str:
        st = self.get(style)
        parts = [st.get("prompt_prefix", ""), "Scene: " + subject.strip().rstrip(".") + "."]
        if shot:
            parts.append(shot + ".")
        if extra:
            parts.append(extra)
        parts.append(st.get("prompt_suffix", ""))
        return " ".join(p for p in parts if p).strip()

    def background_prompt(self, style: str, subject: str) -> str:
        st = self.get(style)
        lead = st.get("background_prefix") or st.get("prompt_prefix", "")
        return f"{lead} Scene: {subject.strip().rstrip('.')}. {st.get('background_suffix', '')}".strip()

    def layer_prompt(self, style: str, subject: str, kind: str = "character") -> str:
        st = self.get(style)
        suffix = st.get("prop_suffix" if kind == "prop" else "character_suffix", "")
        lead = st.get("prop_prefix" if kind == "prop" else "character_prefix") or st.get("prompt_prefix", "")
        return f"{lead} Subject: {subject.strip().rstrip('.')}. {suffix}".strip()
