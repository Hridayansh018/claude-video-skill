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


WALK_SPEED = 0.26     # frame widths per second
RUN_SPEED = 0.62
WALK_PERIOD = 0.24    # seconds per step picture
RUN_PERIOD = 0.13


def _mouth(words, voice_off, a, b):
    """Mouth-open intervals (scene time) for words spoken between a and b: quick flaps, like cartoons."""
    out = []
    for w in words:
        ws, we = voice_off + w["start"], voice_off + w["end"]
        if we <= a or ws >= b:
            continue
        t = max(ws, a)
        end = min(we, b)
        while t < end - 0.04:
            out.append([round(t, 3), round(min(end, t + 0.1), 3)])
            t += 0.17
    return out


def resolve(project: dict, plan: dict, voices: dict) -> list[str]:
    """Fill keyframes + animation (walk cycles, talking mouth, gestures) for every pop-up layer."""
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
        voice_end = voice_off + (words[-1]["end"] if words else scene_len)
        snd = sc.setdefault("sfx", [])
        last = 0.0
        for k, layer in enumerate(ov["layers"]):
            pu = layer.get("popup")
            if pu is None or layer.get("keyframes"):
                continue
            when = lambda v, after, default: _when(v, words, voice_off, scene_len, after, default)
            default_at = min(scene_len * 0.6, 0.4 + k * 1.2)
            t0 = max(0.0, when(pu.get("at"), last, default_at) - 0.15)
            t0 = min(t0, max(0.0, scene_len - 1.0))
            last = t0 + 0.2
            is_char = layer["kind"] == "character"
            x, y = float(pu.get("x", 0.5)), float(pu.get("y", 0.94 if is_char else 0.55))
            d = str(pu.get("from", "bottom"))
            rest = {"x": x, "y": y, "scale": 1.0, "opacity": 1.0, "rot": float(pu.get("rot", 0.0))}
            anim = {"walk": [], "gestures": [], "mouth": [], "facing": int(pu.get("face", 1))}
            sound = pu.get("sfx", True)
            gait_in = d.startswith(("walk", "run"))
            if gait_in:
                # walks / runs in from the side named (walk_left = comes in from the left edge)
                run = d.startswith("run")
                side = "left" if d.endswith("left") else "right"
                start_x = -0.12 - float(layer.get("height", 0.6)) * 0.3 if side == "left" else 1.12 + float(layer.get("height", 0.6)) * 0.3
                dur = min(4.5, max(1.0, abs(x - start_x) / (RUN_SPEED if run else WALK_SPEED)))
                direction = 1 if side == "left" else -1
                kfs = [dict(rest, x=start_x, t=0.0), dict(rest, x=start_x, t=round(t0, 3)),
                       dict(rest, t=round(t0 + dur, 3), ease="linear")]
                anim["walk"].append({"from": round(t0, 3), "to": round(t0 + dur, 3), "dir": direction,
                                     "frames": ["run1", "run2"] if run else ["walk1", "walk2"],
                                     "period": RUN_PERIOD if run else WALK_PERIOD})
                if sound:
                    _steps(snd, t0, t0 + dur, RUN_PERIOD if run else WALK_PERIOD, run)
                t_in = t0 + dur
            else:
                off = dict(rest, **_offscreen(d, layer))
                kfs = [dict(off, t=0.0), dict(off, t=round(t0, 3))]
                if d == "scale":
                    kfs += [dict(rest, t=round(t0 + 0.3, 3), scale=1.1, ease="easeOutCubic"),
                            dict(rest, t=round(t0 + 0.48, 3), ease="easeInOutSine")]
                    t_in = t0 + 0.48
                else:
                    kfs += [dict(rest, t=round(t0 + ENTER, 3), ease="easeOutBack")]
                    t_in = t0 + ENTER
                if sound:
                    if d not in ("scale", "fade"):
                        snd.append({"name": "slide_soft", "at": round(t0, 3), "gain_db": -3})
                    if d != "fade":
                        snd.append({"name": pu.get("sound", "pop_soft"),
                                    "at": round(t0 + (0.26 if d == "scale" else ENTER - 0.1), 3), "gain_db": 0})
            # ---- walks inside the scene: {"to": 0.7, "at": "word", "dur": 2.5, "run": false}
            cur_x = x
            t_last = t_in
            for wk in (layer.get("walk") if isinstance(layer.get("walk"), list) else [layer["walk"]] if layer.get("walk") else []):
                run = bool(wk.get("run"))
                to_x = float(wk["to"])
                ts = max(t_last + 0.1, when(wk.get("at"), t_last, t_last + 0.4))
                dur = float(wk.get("dur") or min(5.0, max(0.8, abs(to_x - cur_x) / (RUN_SPEED if run else WALK_SPEED))))
                kfs += [dict(rest, x=cur_x, t=round(ts, 3)), dict(rest, x=to_x, t=round(ts + dur, 3), ease="linear")]
                anim["walk"].append({"from": round(ts, 3), "to": round(ts + dur, 3), "dir": 1 if to_x >= cur_x else -1,
                                     "frames": ["run1", "run2"] if run else ["walk1", "walk2"],
                                     "period": RUN_PERIOD if run else WALK_PERIOD})
                if sound:
                    _steps(snd, ts, ts + dur, RUN_PERIOD if run else WALK_PERIOD, run)
                cur_x, t_last = to_x, ts + dur
            rest_end = dict(rest, x=cur_x)
            # ---- talking: true (the whole narration while on screen) or {"from": "word", "to": "word"}
            tk = layer.get("talk")
            if tk:
                a = t_in if tk is True else when(tk.get("from"), t_in, t_in)
                bb = voice_end if tk is True else when(tk.get("to"), a, voice_end)
                anim["mouth"] = _mouth(words, voice_off, a, max(a, bb))
            # ---- gestures: [{"at": "look", "pose": "point", "dur": 1.8}]
            for g in layer.get("gestures", []):
                ga = when(g.get("at"), t_in, t_in + 0.5)
                anim["gestures"].append({"from": round(ga, 3), "to": round(ga + float(g.get("dur", 1.8)), 3), "pose": g["pose"]})
            # ---- leave, or idle to the end
            t_out = when(pu.get("out", "end"), t_last, scene_len)
            how_out = pu.get("out_to")  # walk_left / walk_right / bottom / fade ...
            if t_out < scene_len - 0.05:
                t_out = max(t_last + 0.4, t_out)
                if how_out and str(how_out).startswith(("walk", "run")):
                    run = str(how_out).startswith("run")
                    side = "left" if str(how_out).endswith("left") else "right"
                    end_x = -0.3 if side == "left" else 1.3
                    dur = min(4.0, max(0.8, abs(end_x - cur_x) / (RUN_SPEED if run else WALK_SPEED)))
                    kfs += [dict(rest_end, t=round(t_out, 3)), dict(rest_end, x=end_x, t=round(t_out + dur, 3), ease="linear")]
                    anim["walk"].append({"from": round(t_out, 3), "to": round(t_out + dur, 3), "dir": 1 if side == "right" else -1,
                                         "frames": ["run1", "run2"] if run else ["walk1", "walk2"],
                                         "period": RUN_PERIOD if run else WALK_PERIOD})
                    if sound:
                        _steps(snd, t_out, t_out + dur, RUN_PERIOD if run else WALK_PERIOD, run)
                else:
                    off = dict(rest_end, **_offscreen(how_out or (d if not gait_in else "bottom"), layer))
                    kfs += [dict(rest_end, t=round(t_out, 3), y=y - 0.006, ease="easeInOutSine"),
                            dict(off, t=round(t_out + 0.4, 3), ease="easeInCubic")]
            else:
                kfs += [dict(rest_end, t=round(scene_len + 0.5, 3), y=y - 0.006, scale=1.012, ease="easeInOutSine")]
            layer["keyframes"] = sorted(kfs, key=lambda q: q["t"])
            layer["anim"] = anim
            layer["auto_sfx"] = False
            what = "walks in" if gait_in and not d.startswith("run") else "runs in" if gait_in else "pops in"
            notes.append(f"{sc['id']}: '{layer['id']}' {what} at {t0:.2f}s" +
                         (f" on \"{pu['at']}\"" if isinstance(pu.get("at"), str) else "") +
                         (f", walks {len(anim['walk']) - int(gait_in)}x" if len(anim["walk"]) > int(gait_in) else "") +
                         (", talks" if anim["mouth"] else "") +
                         (f", gestures {', '.join(g['pose'] for g in anim['gestures'])}" if anim["gestures"] else ""))
    return notes


def _steps(snd: list, a: float, b: float, period: float, run: bool):
    """Very soft footsteps, one per step picture (kept quiet: they sit under the narration)."""
    t, i = a + period * 0.5, 0
    while t < b:
        snd.append({"name": "step_soft", "at": round(t, 3), "gain_db": (-4 if run else -7) - (i % 2) * 1.5})
        t += period
        i += 1
