"""Cast: recurring characters that keep the same look in every scene.

project.json:
  "cast": {
    "socrates": {"look": "an old bald stick figure philosopher with a big white beard, white toga, barefoot"}
  }
A layer then says  {"id": "socrates", "cast": "socrates", ...}  instead of describing an image.

Pictures made for each cast member (only the ones a scene actually uses):
  cast_<name>            master: standing, three-quarter view facing right, on a green screen
  cast_<name>_<pose>     same character in another pose, made in Google Flow WITH the master
                         attached as a reference image (keeps face, clothes and colours identical)
"""

from __future__ import annotations

import re

# standard poses. Walk/run frames face RIGHT (the engine mirrors them for walking left).
POSES: dict[str, str] = {
    "base":  "standing relaxed, full body, three-quarter view turned slightly to the right, arms at the sides",
    "walk1": "walking to the right in side view, LEFT leg stepping forward and right leg behind, right arm swinging forward",
    "walk2": "walking to the right in side view, RIGHT leg stepping forward and left leg behind, left arm swinging forward",
    "run1":  "running fast to the right in side view, body leaning forward, left knee up high, arms pumping",
    "run2":  "running fast to the right in side view, body leaning forward, right knee up high, arms pumping the other way",
    "talk":  "EXACTLY the same pose, framing and size as the reference image; change ONLY the mouth: wide open as if speaking",
    "point": "pointing forward and up with one hand, the other hand on the hip",
    "cheer": "both arms raised high in celebration, big open smile",
    "wave":  "waving hello with one raised hand, friendly smile",
    "think": "one hand on the chin, thinking, eyes looking up",
    "shock": "shocked: both hands raised, mouth wide open, eyes wide, leaning back",
    "sad":   "sad: head down, shoulders slumped, frowning",
    "angry": "angry: fists clenched, eyebrows down, shouting",
    "fight": "battle stance, weapon raised high ready to strike, shield forward",
    "bow":   "bowing politely with one hand on the chest",
    "sit":   "sitting cross-legged on the ground",
    "kneel": "kneeling on one knee, head bowed",
    "fall":  "falling backwards, arms flailing, surprised face",
}

KEYS = {
    "green":   ("chroma-key green", "#00B140"),
    "magenta": ("chroma-key magenta", "#FF00FF"),
}
_GREENISH = re.compile(r"\b(green|olive|tree|trees|leaf|leaves|leafy|grass|grassy|bush|vine|vines|laurel|wreath|"
                       r"frog|lizard|snake|emerald|jade|lime|moss|mossy|cactus|fern|ivy|herb|herbs|seaweed|"
                       r"plant|plants|forest|jungle|cucumber|pear|apple|teal|turquoise)\b", re.I)


def key_for(text: str, forced: str | None = None) -> str:
    """Green screen, unless the subject itself is green (then magenta)."""
    if forced in KEYS:
        return forced
    return "magenta" if _GREENISH.search(text or "") else "green"


def screen_text(key: str) -> str:
    name, hexv = KEYS[key]
    return (f"on a solid flat {name} background ({hexv}): the whole background is one even flat colour, "
            "no shadow, no floor, no ground, no gradient, no texture, no scenery, no text")


def job_id(cast: str, pose: str) -> str:
    return f"cast_{cast}" if pose in (None, "", "base") else f"cast_{cast}_{pose}"


def pose_text(member: dict, pose: str) -> str:
    return (member.get("poses") or {}).get(pose) or POSES.get(pose) or pose.replace("_", " ")


def master_prompt(prefix: str, member: dict, key: str) -> str:
    return (f"{prefix} Subject: {member['look'].strip().rstrip('.')}. Pose: {pose_text(member, 'base')}. "
            f"A single character only, the whole body from the top of the head to the feet, centred, nothing cropped, "
            f"{screen_text(key)}.")


def pose_prompt(prefix: str, member: dict, pose: str, key: str) -> str:
    return (f"Use the attached reference image. Draw the SAME character as in the reference: identical face, head, "
            f"hair, clothes, colours, proportions and line style ({member['look'].strip().rstrip('.')}). "
            f"New pose: {pose_text(member, pose)}. {prefix.split('.')[0]}. A single character only, the whole body "
            f"visible, centred, nothing cropped, {screen_text(key)}.")


def used_poses(project: dict) -> dict[str, set]:
    """cast name -> set of poses some scene needs (always includes 'base')."""
    out: dict[str, set] = {}
    for sc in project["scenes"]:
        ov = sc.get("overlay") or {}
        for layer in ov.get("layers", []):
            c = layer.get("cast")
            if not c:
                continue
            s = out.setdefault(c, {"base"})
            for p in layer_poses(layer):
                s.add(p)
    return out


def layer_poses(layer: dict) -> set:
    poses = set()
    if layer.get("pose") and layer["pose"] != "base":
        poses.add(layer["pose"])
    pu = layer.get("popup") or {}
    if str(pu.get("from", "")).startswith(("walk", "run")):
        gait = "run" if str(pu["from"]).startswith("run") else "walk"
        poses |= {f"{gait}1", f"{gait}2"}
    for w in _as_list(layer.get("walk")):
        gait = "run" if w.get("run") else "walk"
        poses |= {f"{gait}1", f"{gait}2"}
    if layer.get("talk"):
        poses.add("talk")
    for g in layer.get("gestures", []):
        poses.add(g["pose"])
    return poses


def _as_list(v):
    if not v:
        return []
    return v if isinstance(v, list) else [v]
