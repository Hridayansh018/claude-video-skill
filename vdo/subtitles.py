"""Captions from voiceover word timings: SRT (for editors) and ASS (styled per scene style)."""

from __future__ import annotations

from typing import Iterable


def build_captions(scenes_words: Iterable[tuple[str, str, float, list[dict]]], max_words: int = 7,
                   max_chars: int = 42) -> list[dict]:
    """scenes_words: (scene_id, style, voice_start, words). Returns [{start,end,text,style}]."""
    caps = []
    for sid, style, offset, words in scenes_words:
        cur: list[dict] = []

        def flush():
            if cur:
                caps.append({"scene_id": sid, "style": style, "start": offset + cur[0]["start"],
                             "end": offset + cur[-1]["end"], "text": " ".join(w["text"] for w in cur)})
                cur.clear()

        for w in words:
            cur.append(w)
            text = " ".join(x["text"] for x in cur)
            ends_sentence = w["text"].rstrip("\"')]”’").endswith((".", "!", "?"))
            soft_break = w["text"].endswith((",", ";", ":")) and len(cur) >= max_words - 2
            if ends_sentence or soft_break or len(cur) >= max_words or len(text) >= max_chars:
                flush()
        flush()
    # keep captions readable: minimum 0.8 s, no overlaps
    for i, c in enumerate(caps):
        nxt = caps[i + 1]["start"] if i + 1 < len(caps) else None
        c["end"] = max(c["end"], c["start"] + 0.8)
        if nxt is not None and c["end"] > nxt - 0.02:
            c["end"] = max(c["start"] + 0.3, nxt - 0.02)
    return caps


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_ts(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def to_srt(caps: list[dict]) -> str:
    out = []
    for i, c in enumerate(caps, 1):
        out.append(f"{i}\n{_srt_ts(c['start'])} --> {_srt_ts(c['end'])}\n{c['text']}\n")
    return "\n".join(out)


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def to_ass(caps: list[dict], styles, width: int, height: int) -> str:
    scale = height / 1080.0
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
    ]
    for name in styles.names():
        s = styles.get(name).get("subtitle", {})
        lines.append(
            f"Style: {name},{s.get('font', 'Arial')},{int(s.get('size', 48) * scale)},"
            f"{_ass_color(s.get('color', '#FFFFFF'))},&H000000FF,{_ass_color(s.get('outline', '#000000'))},"
            f"&H80000000,{-1 if s.get('bold') else 0},0,0,0,100,100,0,0,1,{s.get('outline_width', 3) * scale:.1f},"
            f"0,2,80,80,{int(s.get('margin_v', 60) * scale)},1"
        )
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for c in caps:
        text = c["text"].replace("\n", " ").replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{_ass_ts(c['start'])},{_ass_ts(c['end'])},{c['style']},,0,0,0,,{text}")
    return "\n".join(lines) + "\n"
