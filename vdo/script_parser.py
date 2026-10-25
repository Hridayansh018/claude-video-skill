"""Turn a written script (Markdown or plain text) into a project file.

Understands the scene format used in our scripts:

    #### Scene 3 (0:40 – 1:00)
    * **Voiceover:** Then, around 1200 BC ...
    * **Video Prompt:** *A massive Mycenaean citadel ...*
    * **Style:** stickman            (optional)
    * **Images:** 3                  (optional: how many pictures to generate)
    * **SFX:** fire, crowd           (optional: ambience / effects tags)
    * **Popups:** philosopher = an old bearded philosopher in a toga pointing up @ Socrates;
                  scroll = a rolled parchment scroll (prop) @ questions
                                     (optional: characters/objects that pop in over the picture,
                                      "name = description @ word it appears on"; "(prop)" marks an object)
    * **Clip:** clips/s03.mp4        (optional: an animated video clip used instead of pictures)

Plain text without scene headings is split into one scene per paragraph.
"""

from __future__ import annotations

import re
from typing import Optional

SCENE_RE = re.compile(
    r"^#{1,6}\s*Scene\s+(\d+)\s*(?:\((\d+:\d{2}(?::\d{2})?)\s*[–—\-–—to]+\s*(\d+:\d{2}(?::\d{2})?)\))?",
    re.IGNORECASE,
)
PART_RE = re.compile(r"^#{1,6}\s*(Part\s+\d+[^\n]*)", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*[\*\-]?\s*\*\*\s*([A-Za-z ]+?)\s*:\s*\*\*\s*(.*)$")
ANCHOR_RE = re.compile(r"Master Style Anchor:\*\*\s*(.+)$", re.IGNORECASE)


def _ts(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    parts = [float(x) for x in s.split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[>\s]*", "", text)
    text = text.replace("**", "")
    text = re.sub(r"(?<![\w])\*(.+?)\*(?![\w])", r"\1", text)   # *italic*
    text = re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"\1", text)
    text = text.strip().strip("*").strip()
    return re.sub(r"\s+", " ", text)


def _parse_popups(val: str) -> list[dict]:
    out = []
    for item in re.split(r";", val):
        item = item.strip().strip("-* ").strip()
        if not item:
            continue
        cue = None
        if "@" in item:
            item, cue = item.rsplit("@", 1)
            cue = cue.strip().strip('"').strip("'") or None
        name, desc = (item.split("=", 1) if "=" in item else ("", item))
        desc = desc.strip()
        kind = "character"
        if re.search(r"\((prop|object|item)\)", desc, re.I):
            kind = "prop"
            desc = re.sub(r"\s*\((prop|object|item)\)", "", desc, flags=re.I).strip()
        name = re.sub(r"[^a-z0-9]+", "_", (name.strip() or desc.split()[0] if desc else "layer").lower()).strip("_")
        out.append({"id": name or "layer", "kind": kind, "prompt": desc, "at": cue})
    return out


def _overlay_from_popups(popups: list[dict], visual: Optional[str]) -> dict:
    slots = {1: [0.5], 2: [0.3, 0.7], 3: [0.22, 0.5, 0.78]}
    xs = slots.get(len(popups)) or [0.15 + 0.7 * i / max(1, len(popups) - 1) for i in range(len(popups))]
    layers, used = [], set()
    for p, x in zip(popups, xs):
        lid = p["id"]
        while lid in used:
            lid += "_2"
        used.add(lid)
        prop = p["kind"] == "prop"
        layers.append({"id": lid, "kind": p["kind"], "image": {"prompt": p["prompt"]},
                       "height": 0.3 if prop else 0.62,
                       "popup": {"at": p["at"], "x": x, "y": 0.6 if prop else 0.95, "from": "scale" if prop else "bottom"}})
    return {"background": {"prompt": visual} if visual else None, "background_motion": "push_in", "layers": layers}


def parse_script(text: str) -> dict:
    """Return {'scenes': [...], 'style_anchor': str|None}."""
    lines = text.splitlines()
    scenes: list[dict] = []
    cur: Optional[dict] = None
    part: Optional[str] = None
    anchor = None
    last_field = None

    for raw in lines:
        line = raw.rstrip()
        m_anchor = ANCHOR_RE.search(line)
        if m_anchor:
            anchor = _clean(m_anchor.group(1))
            continue
        m_part = PART_RE.match(line)
        if m_part:
            part = re.sub(r"\s*\([^)]*\d:\d{2}[^)]*\)\s*$", "", _clean(m_part.group(1)))
            continue
        m = SCENE_RE.match(line)
        if m:
            if cur:
                scenes.append(cur)
            start, end = _ts(m.group(2)), _ts(m.group(3))
            cur = {"number": int(m.group(1)), "voiceover": "", "visual": None, "chapter": part}
            if start is not None and end is not None and end > start:
                cur["duration"] = round(end - start, 3)
            last_field = None
            continue
        if cur is None:
            continue
        f = FIELD_RE.match(line)
        if f:
            key, val = f.group(1).strip().lower(), _clean(f.group(2))
            last_field = key
            if key.startswith("voice"):
                cur["voiceover"] = val
            elif "prompt" in key or key in ("visual", "image", "video"):
                cur["visual"] = val
            elif key == "style":
                cur["style"] = val.lower()
            elif key in ("images", "image count"):
                try:
                    cur["image_count"] = int(re.findall(r"\d+", val)[0])
                except IndexError:
                    pass
            elif key in ("sfx", "sound", "sounds", "ambience"):
                tags = [t.strip().lower() for t in re.split(r"[,;]", val) if t.strip()]
                if tags:
                    cur["ambience"] = tags[0]
                    cur["sfx"] = tags[1:]
            elif key in ("popups", "popup", "pop ups", "pop-ups", "characters", "overlays"):
                cur["popups"] = _parse_popups(val)
            elif key in ("clip", "video clip", "veo"):
                cur["clip"] = val.strip("` ")
            elif key in ("duration",):
                try:
                    cur["duration"] = float(re.findall(r"[\d.]+", val)[0])
                except IndexError:
                    pass
            continue
        # continuation lines of a multi-line field
        if line.strip() and last_field and not line.lstrip().startswith(("#", "---")):
            if last_field.startswith("voice"):
                cur["voiceover"] = (cur["voiceover"] + " " + _clean(line)).strip()
            elif "prompt" in last_field:
                cur["visual"] = ((cur["visual"] or "") + " " + _clean(line)).strip()
            elif last_field.startswith(("popup", "pop", "character", "overlay")):
                cur["popups"] = cur.get("popups", []) + _parse_popups(_clean(line))
    if cur:
        scenes.append(cur)

    if not scenes:  # plain text: one scene per paragraph
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        scenes = [{"number": i + 1, "voiceover": _clean(p), "visual": None} for i, p in enumerate(paras)]
    return {"scenes": scenes, "style_anchor": anchor}


def build_project(
    text: str,
    name: str,
    default_style: str = "stickman",
    style_map: Optional[dict[int, str]] = None,
    image_duration: float = 4.0,
    scene_range: Optional[tuple[int, int]] = None,
    use_anchor: bool = False,
    outputs: Optional[list[str]] = None,
    image_provider: Optional[str] = None,
) -> dict:
    parsed = parse_script(text)
    scenes_out = []
    for sc in parsed["scenes"]:
        n = sc["number"]
        if scene_range and not (scene_range[0] <= n <= scene_range[1]):
            continue
        entry = {"id": f"s{n:02d}", "voiceover": sc["voiceover"]}
        if sc.get("duration"):
            entry["duration"] = sc["duration"]
        if sc.get("visual"):
            entry["visual"] = sc["visual"]
        style = (style_map or {}).get(n) or sc.get("style")
        if style:
            entry["style"] = style
        for k in ("image_count", "ambience", "sfx", "clip"):
            if sc.get(k):
                entry[k] = sc[k]
        if sc.get("popups"):
            entry["overlay"] = _overlay_from_popups(sc["popups"], sc.get("visual"))
            if entry["overlay"]["background"] is None:
                entry["overlay"].pop("background")
        if sc.get("chapter") and (not scenes_out or scenes_out[-1].get("_chapter") != sc["chapter"]):
            entry["title"] = sc["chapter"]
        entry["_chapter"] = sc.get("chapter")
        scenes_out.append(entry)
    for e in scenes_out:
        e.pop("_chapter", None)
    project = {
        "name": name,
        "default_style": default_style,
        "image_duration": image_duration,
        "outputs": outputs or ["ffmpeg"],
        "scenes": scenes_out,
    }
    if image_provider:
        project["image_provider"] = image_provider
    if use_anchor and parsed["style_anchor"]:
        project["style_overrides"] = {default_style: {"prompt_prefix": parsed["style_anchor"]}}
    return project
