"""The duration rule: decide how many pictures each scene shows and for how long.

For each scene (length D, preferred picture time T, style limits min/max):

1. cuts = floor(D / T); leftover = D - cuts*T
   - leftover >= T/2  -> one more cut, time shared evenly
   - leftover <  T/2  -> keep the cut count, every picture is held a little longer (stretch)
   - then clamp so each hold stays within the style's [min, max]
2. Fewer pictures than cuts -> hold each D/N if that is within max (stretch); otherwise
   reuse pictures as wide / medium / close crops so nothing freezes on screen.
3. "continue": true on a scene (or a scene with no pictures of its own) carries the
   previous scene's last picture across the boundary (up to max), then crops of it.
4. Every cut inside a scene moves to the nearest sentence/comma break (else any word
   gap) within +-snap_window, and never below min_cut.
"""

from __future__ import annotations

import math
from typing import Optional


def scene_windows(project: dict, voices: dict) -> list[dict]:
    tm = project["timing"]
    out, t = [], 0.0
    for sc in project["scenes"]:
        vo = voices.get(sc["id"])
        vo_len = vo["duration"] if vo else 0.0
        need = (tm["voice_offset"] + vo_len + tm["scene_padding"]) if vo else 0.0
        if sc.get("duration") and tm["duration_mode"] == "script":
            length = max(float(sc["duration"]), need)
        else:
            length = need if vo else float(sc["duration"])
        out.append({"id": sc["id"], "index": sc["index"], "start": round(t, 3), "end": round(t + length, 3),
                    "voice_start": round(t + tm["voice_offset"], 3) if vo else None, "style": sc["style"]})
        t += length
    return out


def _cut_count(D: float, T: float, hmin: float, hmax: float) -> int:
    k = int(D // T)
    r = D - k * T
    if k == 0:
        k = 1
    elif r >= T / 2:
        k += 1
    if D / k < hmin:
        k = max(1, int(D // hmin))
    if D / k > hmax:
        k = math.ceil(D / hmax)
    return k


def plan_scene(D: float, T: float, hmin: float, hmax: float, n_explicit: Optional[int],
               image_count: Optional[int], max_images: int) -> tuple[int, int, list[str]]:
    """Return (cuts, pictures_in_pool, notes)."""
    notes = []
    k = _cut_count(D, T, hmin, hmax)
    if n_explicit:
        n = n_explicit
        if n >= k:
            if D / n >= hmin:
                k = n
            else:
                k = max(1, int(D // hmin))
                notes.append(f"{n} images given but only {k} fit at >= {hmin}s each; extra images unused")
            return k, min(n, k), notes
        if D / n <= hmax:
            notes.append(f"stretch: {n} images held {D / n:.2f}s each")
            return n, n, notes
        notes.append(f"{n} images for {k} cuts: reusing them as crops")
        return k, n, notes
    if image_count:
        if image_count > k and D / image_count >= hmin:
            k = image_count
        g = min(image_count, k)
    else:
        g = min(k, max_images)
    if g < k:
        notes.append(f"{g} pictures for {k} cuts: extra cuts use wide/medium/close crops")
    return k, g, notes


def _gaps(words: list[dict], offset: float) -> list[tuple[float, int]]:
    """(time, priority) of breaks between words; priority 2 sentence, 1 comma, 0 plain."""
    out = []
    for a, b in zip(words, words[1:]):
        t = offset + (a["end"] + b["start"]) / 2
        txt = a["text"].rstrip("\"')]”’")
        pri = 2 if txt.endswith((".", "!", "?")) else 1 if txt.endswith((",", ";", ":", "—", "-")) else 0
        out.append((t, pri))
    return out


def _snap(bounds: list[float], gaps: list[tuple[float, int]], window: float, min_cut: float,
          lo: float, hi: float) -> list[float]:
    snapped = list(bounds)
    for i in range(1, len(bounds) - 1):  # inner boundaries only
        b = bounds[i]
        best = None
        for pri_needed, win in ((2, window), (1, window), (0, window / 2)):
            cands = [(abs(t - b), t) for t, p in gaps if p >= pri_needed and abs(t - b) <= win]
            if cands:
                best = min(cands)[1]
                break
        if best is None:
            continue
        prev_b = snapped[i - 1]
        next_b = bounds[i + 1]
        if best - prev_b >= min_cut and next_b - best >= min_cut and lo < best < hi:
            snapped[i] = round(best, 3)
    return snapped


def build_plan(project: dict, styles, voices: dict) -> dict:
    windows = scene_windows(project, voices)
    T_default = float(project["image_duration"])
    tm = project["timing"]
    cuts: list[dict] = []
    pools: dict[str, dict] = {}
    notes: dict[str, list[str]] = {}
    motion_counter = 0

    for sc, win in zip(project["scenes"], windows):
        st = styles.get(sc["style"])
        hmin, hmax = st["hold"]["min"], st["hold"]["max"]
        T = float(sc.get("image_duration") or T_default)
        D = win["end"] - win["start"]
        sc_notes = notes.setdefault(sc["id"], [])

        # ---- animated clip scene (e.g. a Google Flow / Veo video): one cut for the whole scene
        if sc.get("clip"):
            pools[sc["id"]] = {"owner": sc["id"], "count": 1, "style": sc["style"], "overlay": False, "clip": True}
            cuts.append(_cut(sc, win, win["start"], win["end"], sc["id"], 0, 0, "clip", motion_counter))
            motion_counter += 1
            continue

        # ---- overlay scene: one background cut for the whole scene
        if sc.get("overlay"):
            pools[sc["id"]] = {"owner": sc["id"], "count": 1, "style": sc["style"], "overlay": True}
            cuts.append(_cut(sc, win, win["start"], win["end"], sc["id"], 0, 0, "overlay", motion_counter))
            motion_counter += 1
            continue

        explicit = len(sc["images"]) if sc.get("images") else None
        carry = sc.get("continue") or (not explicit and not sc.get("visual"))
        if carry and cuts:
            prev = cuts[-1]
            pool_id = prev["pool"]
            pool = pools[pool_id]
            # extend the previous picture across the boundary, up to the style max
            prev_len = prev["end"] - prev["start"]
            extend_to = min(win["end"], prev["start"] + max(hmax, prev_len))
            prev["end"] = round(extend_to, 3)
            prev["spans_scenes"] = prev.get("spans_scenes", [prev["scene_id"]]) + [sc["id"]]
            sc_notes.append(f"carried previous picture {extend_to - win['start']:.2f}s into this scene")
            rem = win["end"] - extend_to
            if rem >= tm["min_cut"]:
                k = _cut_count(rem, T, hmin, hmax)
                bounds = [extend_to + rem * j / k for j in range(k + 1)]
                vo = voices.get(sc["id"])
                if vo:
                    bounds = _snap(bounds, _gaps(vo["words"], win["voice_start"]), tm["snap_window"],
                                   max(tm["min_cut"], hmin * 0.7), win["start"], win["end"])
                start_j = prev["image"] + 1 + prev["variant"] * pool["count"]
                for j in range(k):
                    jj = start_j + j
                    cuts.append(_cut(sc, win, bounds[j], bounds[j + 1], pool_id, jj % pool["count"],
                                     max(1, jj // pool["count"]), "image", motion_counter))
                    motion_counter += 1
            elif rem > 0:
                prev["end"] = win["end"]
            continue

        k, g, n = plan_scene(D, T, hmin, hmax, explicit, sc.get("image_count"), project["max_images_per_scene"])
        sc_notes.extend(n)
        pools[sc["id"]] = {"owner": sc["id"], "count": g, "style": sc["style"], "overlay": False}
        bounds = [win["start"] + D * j / k for j in range(k + 1)]
        vo = voices.get(sc["id"])
        if vo and k > 1:
            bounds = _snap(bounds, _gaps(vo["words"], win["voice_start"]), tm["snap_window"],
                           max(tm["min_cut"], hmin * 0.7), win["start"], win["end"])
        for j in range(k):
            cuts.append(_cut(sc, win, bounds[j], bounds[j + 1], sc["id"], j % g, j // g, "image", motion_counter))
            motion_counter += 1

    _assign_transitions(project, styles, cuts)
    return {"scenes": windows, "cuts": cuts, "pools": pools, "notes": notes,
            "duration": windows[-1]["end"] if windows else 0.0}


def quantize(plan: dict, fps: int) -> None:
    """Snap cut boundaries to whole frames and transitions to an even number of frames,
    so clips and transitions line up exactly in every backend."""
    q = lambda t: round(round(t * fps) / fps, 6)
    for c in plan["cuts"]:
        c["start"], c["end"] = q(c["start"]), q(c["end"])
        tr = c.get("transition_in")
        if tr and tr["duration"] > 0:
            frames = max(2, int(round(tr["duration"] * fps / 2)) * 2)
            tr["duration"] = round(frames / fps, 6)
    plan["duration"] = q(plan["duration"])
    if plan["cuts"]:
        plan["cuts"][-1]["end"] = plan["duration"]


def _cut(sc, win, start, end, pool, image, variant, kind, motion_idx) -> dict:
    return {"scene_id": sc["id"], "scene_index": sc["index"], "style": sc["style"], "kind": kind,
            "pool": pool, "image": image, "variant": variant,
            "start": round(start, 3), "end": round(end, 3), "motion_idx": motion_idx,
            "motion": sc.get("motion"), "transition_in": None}


def _assign_transitions(project, styles, cuts):
    for i, c in enumerate(cuts):
        if i == 0:
            continue
        prev = cuts[i - 1]
        st = styles.get(c["style"])
        sc = project["scenes"][c["scene_index"]]
        if prev["scene_id"] == c["scene_id"] or c["scene_id"] in prev.get("spans_scenes", []):
            tr = dict(st["transitions"]["cut"])
            kind = "cut"
        elif prev["style"] != c["style"]:
            tr = dict(sc.get("transition_in") or project["style_change"])
            kind = "style_change"
        else:
            tr = dict(sc.get("transition_in") or st["transitions"]["scene"])
            kind = "scene"
        # never longer than 40% of either neighbouring cut
        slot = min(prev["end"] - prev["start"], c["end"] - c["start"])
        dur = float(tr.get("duration", 0.5))
        if tr.get("type", "cut") == "cut":
            dur = 0.0
        tr["duration"] = round(min(dur, 0.4 * slot), 3)
        tr["kind"] = kind
        c["transition_in"] = tr
