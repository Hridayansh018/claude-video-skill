"""Story types: what kind of story the script tells (war, calm, mystery ...) decides the background music.

Set it yourself:   project.json  "story_type": "war"      (or a script line  **Story Type:** war)
                   one scene     "mood": "tense"          (or a scene line   **Mood:** tense)
or leave "auto": the engine reads each scene's narration and picks the music that fits it, staying with
the overall story type unless a scene clearly says otherwise.
"""

from __future__ import annotations

import re

# music style  ->  words (stems) that suggest it. Earlier entries win ties.
KEYWORDS: dict[str, str] = {
    "war": r"war|wars|warfare|battle\w*|siege\w*|besieg\w*|army|armies|soldier\w*|invad\w*|invasion|conquer\w*|sword\w*|attack\w*|"
           r"fought|fight\w*|warrior\w*|weapon\w*|spear\w*|shield\w*|raid\w*|massacre\w*|crusade\w*|legion\w*|stormed|storming|"
           r"rushed in|charge\w*|slaughter\w*|bomb\w*|missile\w*|troops|general\w*|commander\w*",
    "tense": r"danger\w*|trap\w*|spy|spies|escape\w*|chase\w*|threat\w*|plot\w*|betray\w*|ambush\w*|crept|sneak\w*|hid|hidden|"
             r"hide|fear\w*|panic\w*|warning|suspens\w*|infiltrat\w*|secretly|trick\w*|deceiv\w*|deception|disguis\w*",
    "dark": r"death|dead|doom\w*|dark|darkness|evil|curse\w*|plague\w*|ruin\w*|destroy\w*|flames|burn\w*|cruel\w*|tyrant\w*|"
            r"horror|terror|demon\w*|grave\w*|haunt\w*|nightmare\w*|corpse\w*",
    "sad": r"died|tragic|tragedy|grief|mourn\w*|loss|lost|defeat\w*|exile\w*|famine|suffer\w*|sorrow\w*|farewell|orphan\w*|"
           r"weep\w*|wept|cried|funeral|bitter",
    "triumph": r"victor\w*|triumph\w*|celebrat\w*|cheer\w*|crowned|glory|glorious|won|champion\w*|liberat\w*|freedom|"
               r"success\w*|achiev\w*|conquered|hero\w*|parade",
    "mystery": r"mystery|mysteries|mysterious|unknown|riddle\w*|vanish\w*|disappear\w*|unexplained|puzzle\w*|clever|"
               r"enigma\w*|strange\w*|whisper\w*|forgotten|lost city|legend\w*|myth\w*",
    "adventure": r"journey\w*|voyage\w*|explor\w*|expedition\w*|quest\w*|travel\w*|sailed|trek\w*|odyssey|adventur\w*|"
                 r"discover\w*|set out|pioneer\w*",
    "epic": r"empire\w*|kingdom\w*|mighty|dynasty|dynasties|monument\w*|civili[sz]ation\w*|rose to|rise of|fall of|"
            r"age of|great\w*|ancient|history|historic\w*|pharaoh\w*|emperor\w*|temple\w*",
    "wonder": r"invent\w*|science|scientif\w*|marvel\w*|wonder\w*|curious|knowledge|philosoph\w*|ideas?|question\w*|"
              r"discovery|genius|mathematic\w*|astronom\w*",
    "calm": r"peace\w*|quiet\w*|calm\w*|gentle\w*|village\w*|farm\w*|daily life|nature|garden\w*|simple|harvest\w*|morning|"
            r"serene|meadow\w*|family|children|childhood|cozy",
}
ORDER = list(KEYWORDS)
_RX = {k: re.compile(rf"\b(?:{v})\b", re.I) for k, v in KEYWORDS.items()}


def scores(text: str) -> dict[str, int]:
    return {k: len(rx.findall(text or "")) for k, rx in _RX.items()}


def best(sc: dict[str, int], minimum: int = 1) -> str | None:
    top = max(sc.values()) if sc else 0
    if top < minimum:
        return None
    for k in ORDER:               # priority order breaks ties
        if sc[k] == top:
            return k
    return None


def story_type(scenes: list[dict], given: str | None = None) -> str:
    if given and given != "auto":
        return given
    total: dict[str, int] = {}
    for sc in scenes:
        for k, v in scores(f"{sc.get('voiceover') or ''} {sc.get('visual') or ''}").items():
            total[k] = total.get(k, 0) + v
    return best(total) or "calm"


def scene_moods(scenes: list[dict], given: str | None = None) -> tuple[str, list[str]]:
    """(overall story type, music style per scene). An explicit scene "mood" always wins."""
    base = story_type(scenes, given)
    out = []
    for sc in scenes:
        if sc.get("mood"):
            out.append(sc["mood"])
            continue
        s = scores(f"{sc.get('voiceover') or ''} {sc.get('visual') or ''}")
        pick = best(s, 2)           # a scene must say it clearly (2+ hits) to leave the overall story type
        out.append(pick if pick else base)
    return base, out


def smooth(sections: list[tuple[float, float, str]], min_len: float = 7.0) -> list[tuple[float, float, str]]:
    """Music should not flip every few seconds: a section shorter than min_len joins its neighbour."""
    secs = [list(s) for s in sections]
    changed = True
    while changed and len(secs) > 1:
        changed = False
        for i, (a, b, m) in enumerate(secs):
            if b - a < min_len:
                j = i - 1 if i > 0 else i + 1
                if j == i - 1:
                    secs[j][1] = b
                else:
                    secs[j][0] = a
                del secs[i]
                changed = True
                break
    merged: list[list] = []
    for a, b, m in secs:
        if merged and merged[-1][2] == m:
            merged[-1][1] = b
        else:
            merged.append([a, b, m])
    return [tuple(x) for x in merged]
