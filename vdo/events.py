"""Sound for what the narration talks about: when the voiceover says "the crowd cheered", a cheer plays
under that word. Also picks a quiet ambience bed for a scene from what it describes.

Turn off per project with "audio": {"auto_events": false, "auto_ambience": false}, or per scene with
"auto_sfx": false. Explicit scene "sfx" / "ambience" always win.
"""

from __future__ import annotations

import re

# (regex on a word or two of narration, sound name). First match per word; order = priority.
EVENT_RULES: list[tuple[str, str]] = [
    (r"explo\w*|blast\w*|bomb\w*|erupt\w*|detonat\w*", "blast"),
    (r"thunder\w*|lightning", "thunder"),
    (r"earthquake\w*|tremor\w*|quake\w*", "earthquake"),
    (r"scream\w*|shriek\w*", "scream"),
    (r"applau\w*|clapp\w*", "applause"),
    (r"cheer\w*|hooray|hurrah|victor\w*|triumph\w*|celebrat\w*", "cheer"),
    (r"laugh\w*", "laugh"),
    (r"gasp\w*|astonish\w*", "gasp"),
    (r"clash\w*|fought|fighting|siege\w*|invad\w*|attack\w*|stormed|storming|battle\w*", "sword_clash"),
    (r"sword\w*|blade\w*|unsheath\w*", "sword_draw"),
    (r"arrow\w*|archer\w*", "arrows"),
    (r"cavalry|gallop\w*|chariot\w*", "gallop"),
    (r"drum\w*", "war_drums"),
    (r"trumpet\w*|fanfare|herald\w*|coronat\w*", "fanfare"),
    (r"bell|bells", "bell"),
    (r"gong", "gong"),
    (r"ablaze|flames|inferno|set fire|burst into", "fire_burst"),
    (r"splash\w*|plung\w*|drown\w*", "splash"),
    (r"collaps\w*|crumbl\w*|smash\w*|shatter\w*", "crash"),
    (r"gold|coins?|treasure\w*|wealth", "coins"),
    (r"forge\w*|anvil\w*|blacksmith\w*|hammer\w*", "anvil"),
    (r"heartbeat", "heartbeat"),
    (r"magic\w*|miracle\w*|oracle\w*", "sparkle"),
]

# Beds that never contain voices. Crowd / market / battle beds (which sound like people talking) are NOT picked
# automatically; ask for them with a scene "ambience": "crowd".
AMBIENCE_RULES: list[tuple[str, str]] = [
    (r"storm\w*|thunder\w*|tempest", "rain"),
    (r"rain\w*", "rain"),
    (r"fire|fires|flames?|burning|blaze|forge|torch\w*|campfires?", "fire"),
    (r"sea|seas|ocean\w*|waves?|ships?|sail\w*|fleet\w*|harbou?r\w*|coast\w*|island\w*|beach\w*|navy", "sea"),
    (r"cave\w*|tunnel\w*|underground|dungeon\w*|catacomb\w*|tomb\w*", "cave"),
    (r"forest\w*|woods|garden\w*|farm\w*|fields?|countryside|valley\w*|village\w*|olive", "countryside"),
    (r"night|stars|moon\w*|darkness", "night"),
    (r"wind\w*|mountain\w*|desert\w*|cliff\w*|peak\w*|battlefield|besieg\w*|siege", "wind"),
]

_EV = [(re.compile(rf"^(?:{p})$", re.I), name) for p, name in EVENT_RULES]
_AMB = [(re.compile(rf"\b(?:{p})\b", re.I), name) for p, name in AMBIENCE_RULES]


def _clean(w: str) -> str:
    return re.sub(r"[^A-Za-z']", "", w)


def find_events(words: list[dict], max_events: int = 2, min_gap: float = 3.5) -> list[tuple[float, str, str]]:
    """[(time in voice, sound, word)] for the narration words that name an event."""
    out = []
    used = set()
    for i, w in enumerate(words):
        token = _clean(w["text"])
        two = token + " " + _clean(words[i + 1]["text"]) if i + 1 < len(words) else token
        for rx, name in _EV:
            if rx.match(token) or (" " in rx.pattern and rx.match(two)):
                if name in used or any(abs(w["start"] - t) < min_gap for t, _, _ in out):
                    break
                out.append((w["start"], name, token))
                used.add(name)
                break
        if len(out) >= max_events:
            break
    return out


def pick_ambience(text: str) -> str | None:
    for rx, name in _AMB:
        if rx.search(text or ""):
            return name
    return None
