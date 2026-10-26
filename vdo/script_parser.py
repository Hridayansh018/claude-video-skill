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

    ## Cast                          (optional: recurring characters, drawn the same way every time)
    * socrates: an old bald stick figure philosopher with a big white beard, white toga, barefoot

    then in a scene:  * **Popups:** socrates @ Socrates | walks in from left | talks | points @ question

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
STORY_RE = re.compile(r"^\W*(?:story\s*type|genre|music\s*style)\W*\s*:\**\s*(.+)$", re.IGNORECASE)
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


GESTURE_WORDS = {
    "point": "point", "points": "point", "pointing": "point", "cheer": "cheer", "cheers": "cheer",
    "celebrates": "cheer", "wave": "wave", "waves": "wave", "think": "think", "thinks": "think",
    "shock": "shock", "shocked": "shock", "surprised": "shock", "sad": "sad", "cries": "sad", "angry": "angry",
    "shouts": "angry", "fight": "fight", "fights": "fight", "attacks": "fight", "bow": "bow", "bows": "bow",
    "sit": "sit", "sits": "sit", "kneel": "kneel", "kneels": "kneel", "fall": "fall", "falls": "fall",
}
PLACES = {"left": 0.25, "centre": 0.5, "center": 0.5, "middle": 0.5, "right": 0.75,
          "far left": 0.14, "far right": 0.86}


def _place(word: str):
    word = word.strip().lower()
    if word in PLACES:
        return PLACES[word]
    try:
        return float(word)
    except ValueError:
        return None


def _parse_popups(val: str) -> list[dict]:
    """'name = description @ cue | action | action; ...'  or  'castname @ cue | walks in from left | talks'"""
    out = []
    for item in re.split(r";", val):
        item = item.strip().strip("-* ").strip()
        if not item:
            continue
        parts = [x.strip() for x in item.split("|")]
        head, actions = parts[0], parts[1:]
        cue = None
        if "@" in head:
            head, cue = head.rsplit("@", 1)
            cue = cue.strip().strip('"').strip("'") or None
        name, desc = (head.split("=", 1) if "=" in head else (head, ""))
        desc = desc.strip()
        kind = "character"
        if re.search(r"\((prop|object|item)\)", desc, re.I):
            kind = "prop"
            desc = re.sub(r"\s*\((prop|object|item)\)", "", desc, flags=re.I).strip()
        lid = re.sub(r"[^a-z0-9]+", "_", (name.strip() or (desc.split()[0] if desc else "layer")).lower()).strip("_")
        pop = {"id": lid or "layer", "kind": kind, "prompt": desc, "at": cue, "actions": {}}
        act = pop["actions"]
        for a in actions:
            acue = None
            if "@" in a:
                a, acue = a.rsplit("@", 1)
                acue = acue.strip().strip('"').strip("'") or None
            low = a.lower().strip()
            m = re.match(r"(walks?|runs?) in from (?:the )?(left|right)", low)
            if m:
                act["from"] = ("run_" if m.group(1).startswith("run") else "walk_") + m.group(2)
                continue
            m = re.match(r"(walks?|runs?|moves?) to (?:the )?(.+)", low)
            if m and _place(m.group(2)) is not None:
                act.setdefault("walk", []).append({"to": _place(m.group(2)), "at": acue,
                                                   "run": m.group(1).startswith("run")})
                continue
            m = re.match(r"(leaves|exits|walks off|runs off|walks out|runs out)(?: to)?(?: the)? ?(left|right)?", low)
            if m:
                act["out"] = acue or "end"
                gait = "run_" if "run" in m.group(1) else "walk_"
                act["out_to"] = gait + (m.group(2) or "right")
                continue
            if low.startswith(("talks", "talk", "speaks", "says")):
                act["talk"] = {"from": acue} if acue else True
                continue
            m = re.match(r"(?:stands |appears |at )(?:on |at )?(?:the )?(.+)", low)
            if m and _place(m.group(1)) is not None:
                act["x"] = _place(m.group(1))
                continue
            word = low.split()[0] if low else ""
            if word in GESTURE_WORDS:
                act.setdefault("gestures", []).append({"pose": GESTURE_WORDS[word], "at": acue})
                continue
            if low in ("pops", "pops up", "pops in"):
                continue
        out.append(pop)
    return out


def _overlay_from_popups(popups: list[dict], visual: Optional[str], cast: dict) -> dict:
    slots = {1: [0.5], 2: [0.3, 0.7], 3: [0.22, 0.5, 0.78]}
    xs = slots.get(len(popups)) or [0.15 + 0.7 * i / max(1, len(popups) - 1) for i in range(len(popups))]
    layers, used = [], set()
    for p, x in zip(popups, xs):
        lid = p["id"]
        while lid in used:
            lid += "_2"
        used.add(lid)
        act = p.get("actions", {})
        prop = p["kind"] == "prop"
        layer = {"id": lid, "kind": p["kind"], "height": 0.3 if prop else 0.62}
        if p["id"] in cast and not p["prompt"]:
            layer["cast"] = p["id"]
        else:
            layer["image"] = {"prompt": p["prompt"] or p["id"].replace("_", " ")}
        layer["popup"] = {"at": p["at"], "x": act.get("x", x), "y": 0.6 if prop else 0.95,
                          "from": act.get("from") or ("scale" if prop else "bottom")}
        if act.get("out"):
            layer["popup"]["out"] = act["out"]
            layer["popup"]["out_to"] = act.get("out_to")
        for k in ("walk", "talk", "gestures"):
            if act.get(k):
                layer[k] = act[k]
        layers.append(layer)
    return {"background": {"prompt": visual} if visual else None, "background_motion": "push_in", "layers": layers}


CAST_HEAD_RE = re.compile(r"^#{1,6}\s*(Cast|Characters)\b", re.I)
CAST_LINE_RE = re.compile(r"^\s*[\*\-]\s*(?:\*\*)?\s*([A-Za-z0-9_ ]+?)\s*(?:\*\*)?\s*[:=]\s*(?:\*\*)?\s*(.+)$")


def parse_script(text: str) -> dict:
    """Return {'scenes': [...], 'style_anchor': str|None}."""
    lines = text.splitlines()
    scenes: list[dict] = []
    cur: Optional[dict] = None
    part: Optional[str] = None
    anchor = None
    story = None
    last_field = None

    cast: dict = {}
    in_cast = False
    for raw in lines:
        line = raw.rstrip()
        if CAST_HEAD_RE.match(line):
            in_cast = True
            continue
        if in_cast:
            if line.lstrip().startswith("#"):
                in_cast = False
            else:
                mc = CAST_LINE_RE.match(line)
                if mc:
                    cname = re.sub(r"[^a-z0-9]+", "_", mc.group(1).strip().lower()).strip("_")
                    cast[cname] = {"look": _clean(mc.group(2))}
                continue
        m_story = STORY_RE.match(line)
        if m_story and cur is None:
            story = _clean(m_story.group(1)).lower().split()[0].strip(".,;")
            continue
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
            elif key in ("mood", "music", "music mood"):
                cur["mood"] = val.lower().split()[0].strip(".,;") if val.strip() else None
            elif key in ("images", "image count"):
                try:
                    cur["image_count"] = int(re.findall(r"\d+", val)[0])
                except IndexError:
                    pass
            elif key in ("sfx", "sound", "sounds", "ambience"):
                from .sfx_lib import BEDS
                for tag in [t.strip() for t in re.split(r"[,;]", val) if t.strip()]:
                    at = None
                    if "@" in tag:
                        tag, at = [x.strip().strip('"') for x in tag.rsplit("@", 1)]
                    tag = tag.lower().replace(" ", "_")
                    if tag in BEDS and at is None and not cur.get("ambience"):
                        cur["ambience"] = tag
                    else:
                        cur.setdefault("sfx", []).append({"name": tag, "at": at} if at else tag)
            elif key in ("popups", "popup", "pop ups", "pop-ups", "characters", "overlays"):
                cur["popups"] = _parse_popups(val)
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
    return {"scenes": scenes, "style_anchor": anchor, "cast": cast, "story_type": story}


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
        if sc.get("mood"):
            entry["mood"] = sc["mood"]
        if sc.get("visual"):
            entry["visual"] = sc["visual"]
        style = (style_map or {}).get(n) or sc.get("style")
        if style:
            entry["style"] = style
        for k in ("image_count", "ambience", "sfx"):
            if sc.get(k):
                entry[k] = sc[k]
        if sc.get("popups"):
            entry["overlay"] = _overlay_from_popups(sc["popups"], sc.get("visual"), parsed["cast"])
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
    if parsed.get("story_type"):
        project["story_type"] = parsed["story_type"]
    if parsed.get("cast"):
        project["cast"] = parsed["cast"]
    if image_provider:
        project["image_provider"] = image_provider
    if use_anchor and parsed["style_anchor"]:
        project["style_overrides"] = {default_style: {"prompt_prefix": parsed["style_anchor"]}}
    return project
