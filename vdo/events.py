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
    (r"chaos|panic\w*|riot\w*|stampede\w*|mayhem|havoc|fled in terror", "chaos"),
    (r"applau\w*|clapp\w*", "applause"),
    (r"celebrat\w*|festival\w*|feast\w*|rejoic\w*|jubila\w*", "celebration"),
    (r"cheer\w*|hooray|hurrah|victor\w*|triumph\w*", "cheer"),
    (r"laugh\w*", "laugh"),
    (r"gasp\w*|shock\w*|astonish\w*", "gasp"),
    (r"battle\w*|war|wars|warfare|fought|fighting|clash\w*|invad\w*|attack\w*|siege\w*", "battle_burst"),
    (r"sword\w*|blade\w*|unsheath\w*", "sword_draw"),
    (r"arrow\w*|archer\w*", "arrows"),
    (r"cavalry|horse\w*|gallop\w*|chariot\w*", "gallop"),
    (r"march\w*|legion\w*|soldiers|troops|army|armies|phalanx", "march"),
    (r"drum\w*", "war_drums"),
    (r"horn\w*", "war_horn"),
    (r"trumpet\w*|fanfare|herald\w*|crown\w*|coronat\w*", "fanfare"),
    (r"bell\w*", "bell"),
    (r"gong", "gong"),
    (r"fire|fires|flame\w*|burn\w*|blaze\w*|torch\w*|ablaze", "fire_burst"),
    (r"splash\w*|plung\w*|dived|drown\w*", "splash"),
    (r"collaps\w*|crash\w*|crumbl\w*|smash\w*|shatter\w*", "crash"),
    (r"gold|coins?|treasure\w*|silver|wealth|riches|trade|traded|merchant\w*", "coins"),
    (r"forge\w*|anvil\w*|blacksmith\w*|hammer\w*", "anvil"),
    (r"heartbeat|heart pounding|heart raced", "heartbeat"),
    (r"magic\w*|divine|oracle\w*|miracle\w*|gods?|goddess\w*", "sparkle"),
]

AMBIENCE_RULES: list[tuple[str, str]] = [
    (r"storm\w*|thunder\w*|tempest", "storm"),
    (r"battle\w*|war|wars|fought|siege\w*|battlefield", "battle"),
    (r"rain\w*", "rain"),
    (r"fire|flames?|burning|blaze|forge", "fire"),
    (r"sea|seas|ocean\w*|waves?|ships?|sail\w*|fleet\w*|harbou?r\w*|coast\w*|island\w*|beach\w*|navy", "sea"),
    (r"market\w*|agora|bazaar|merchant\w*|trade\w*", "market"),
    (r"crowd\w*|city|cities|streets?|citizens|assembly|stadium|games|olympi\w*|theatre|theater", "crowd"),
    (r"forest\w*|woods|garden\w*|farm\w*|fields?|countryside|valley\w*|village\w*|olive", "countryside"),
    (r"night|stars|moon\w*", "night"),
    (r"wind\w*|mountain\w*|desert\w*|cliff\w*|peak\w*", "wind"),
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
