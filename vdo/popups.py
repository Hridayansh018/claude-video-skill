"""Pop-ups: turn a short 'popup' description on an overlay layer into keyframes, timed to the narration.

    {"id": "spartan", "kind": "character", "image": {"prompt": "a Spartan warrior ..."},
     "popup": {"at": "Spartans", "x": 0.3, "y": 0.92, "from": "bottom", "out": "end"}}

at   : seconds from the scene start, or a word / phrase from the voiceover (first match after the
       previous pop-up), e.g. "Spartans" or "the Olympic flame"
from : bottom | top | left | right | scale (grow in with a bounce) | fade
out  : "end" (stay until the scene ends, default), seconds, or a word / phrase - the layer leaves the same way
x, y : where it settles (0-1 of the frame; for characters y is where the feet stand)
"""

from __future__ import annotations

import re
from typing import Optional

ENTER = 0.45


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", s.lower())


def find_phrase(words: list[dict], phrase: str, after: float = -1.0) -> Optional[float]:
    target = [_norm(t) for t in phrase.split() if _norm(t)]
    if not target:
        return None
    toks = [_norm(w["text"]) for w in words]
    for pass_after in (after, -1.0):
        for i in range(len(toks) - len(target) + 1):
            if words[i]["start"] < pass_after:
                continue
            if all(toks[i + k].startswith(target[k]) if k == len(target) - 1 else toks[i + k] == target[k]
                   for k in range(len(target))):
                return words[i]["start"]
    return None


def _when(v, words, voice_off, scene_len, after, default):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if v == "end":
        return scene_len
    t = find_phrase(words, str(v), after - voice_off)
    return default if t is None else voice_off + t


def _offscreen(direction: str, layer: dict) -> dict:
    """Start/finish position fully outside the frame (characters stand on their feet: anchor bottom)."""
    h = float(layer.get("height", 0.6))
    bottom_anchor = layer.get("anchor", "bottom" if layer.get("kind") == "character" else "center") == "bottom"
    below = 1.04 + (h if bottom_anchor else h / 2)
    above = -0.04 - (0 if bottom_anchor else h / 2)
    side = 0.06 + h * 0.9          # generous: wide props
    return {"bottom": {"y": below}, "top": {"y": above}, "left": {"x": -side}, "right": {"x": 1.0 + side},
            "scale": {"scale": 0.05, "opacity": 0.0}, "fade": {"opacity": 0.0}}.get(direction, {"y": below})


def resolve(project: dict, plan: dict, voices: dict) -> list[str]:
    """Fill keyframes for every pop-up layer. Returns notes for the log."""
    notes = []
    windows = {w["id"]: w for w in plan["scenes"]}
    for sc in project["scenes"]:
        ov = sc.get("overlay")
        if not ov:
            continue
        win = windows[sc["id"]]
        scene_len = win["end"] - win["start"]
        words = (voices.get(sc["id"]) or {}).get("words") or []
        voice_off = (win.get("voice_start") or win["start"]) - win["start"]
        last = 0.0
        for k, layer in enumerate(ov["layers"]):
            pu = layer.get("popup")
            if not pu or layer.get("keyframes"):
                continue
            default_at = min(scene_len * 0.6, 0.4 + k * 1.2)
            t0 = max(0.0, _when(pu.get("at"), words, voice_off, scene_len, last, default_at) - 0.15)
            t0 = min(t0, max(0.0, scene_len - 1.0))
            last = t0 + 0.2
            x, y = float(pu.get("x", 0.5)), float(pu.get("y", 0.92 if layer["kind"] == "character" else 0.55))
            d = pu.get("from", "bottom")
            rest = {"x": x, "y": y, "scale": 1.0, "opacity": 1.0, "rot": float(pu.get("rot", 0.0))}
            off = dict(rest, **_offscreen(d, layer))
            kfs = [dict(off, t=0.0), dict(off, t=round(t0, 3))]
            if d == "scale":
                kfs += [dict(rest, t=round(t0 + 0.3, 3), scale=1.12, ease="easeOutCubic"),
                        dict(rest, t=round(t0 + 0.48, 3), ease="easeInOutSine")]
            else:
                kfs += [dict(rest, t=round(t0 + ENTER, 3), ease="easeOutBack")]
            # gentle idle bob so a standing figure never looks frozen
            t_in = kfs[-1]["t"]
            t_out = _when(pu.get("out", "end"), words, voice_off, scene_len, t_in, scene_len)
            if t_out < scene_len - 0.05:
                t_out = max(t_in + 0.4, t_out)
                kfs += [dict(rest, t=round(t_out, 3), y=y - 0.006, ease="easeInOutSine"),
                        dict(off, t=round(t_out + 0.4, 3), ease="easeInBack")]
            else:
                kfs += [dict(rest, t=round(scene_len + 0.5, 3), y=y - 0.008, scale=1.015, ease="easeInOutSine")]
            layer["keyframes"] = kfs
            # sound: whoosh as it moves, pop when it lands (the audio step reads these)
            layer["auto_sfx"] = False
            snd = sc.setdefault("sfx", [])
            if pu.get("sfx", True):
                if d != "scale" and d != "fade":
                    snd.append({"name": "swish", "at": round(t0, 3), "gain_db": -2})
                snd.append({"name": pu.get("sound", "pop"), "at": round(t0 + (0.28 if d == "scale" else ENTER - 0.08), 3),
                            "gain_db": 0})
            notes.append(f"{sc['id']}: '{layer['id']}' pops in at {t0:.2f}s" +
                         (f" on \"{pu['at']}\"" if isinstance(pu.get("at"), str) else ""))
    return notes
