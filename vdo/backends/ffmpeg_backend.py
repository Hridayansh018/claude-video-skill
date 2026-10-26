"""Final MP4 with ffmpeg: join cut clips with xfade transitions, add the mixed audio
(loudness-normalised), optionally burn in styled subtitles. No editor needed."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..util import log

BATCH = 40


def _loudnorm(b, a) -> str:
    """Two-pass loudnorm with a fixed gain: every part of the mix (music included) is raised or lowered by the
    same amount, so a loud effect can never make the music pump up and down."""
    import json, re, subprocess
    tgt = a["target_lufs"]
    base = f"loudnorm=I={tgt}:TP=-1.5:LRA=11"
    try:
        ff = getattr(b.ff, "ffmpeg", None) or getattr(b.ff, "exe", None) or "ffmpeg"
        r = subprocess.run([str(ff), "-hide_banner", "-nostats", "-i", os.path.abspath(b.audio_wav), "-af",
                            base + ":print_format=json", "-f", "null", "-"], capture_output=True, text=True)
        m = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
        return (base + f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except Exception:
        return base


def _chain(ff, segs: list[dict], fps: int, out: str, tmp_dir: Path, tag: str, crf: int = 17,
           preset: str = "medium") -> str:
    """segs: [{path, t_start, t_end, tr_type, tr_dur}] where tr_* is the transition INTO the segment.
    Produces one file covering segs[0].t_start .. segs[-1].t_end."""
    if len(segs) == 1:
        shutil.copyfile(segs[0]["path"], out)
        return out
    if len(segs) > BATCH:
        groups = [segs[i:i + BATCH] for i in range(0, len(segs), BATCH)]
        joined = []
        for gi, g in enumerate(groups):
            p = str(tmp_dir / f"{tag}_b{gi:02d}.mp4")
            _chain(ff, g, fps, p, tmp_dir, f"{tag}_{gi}", max(10, crf - 3), preset)
            joined.append({"path": p, "t_start": g[0]["t_start"], "t_end": g[-1]["t_end"],
                           "tr_type": g[0]["tr_type"], "tr_dur": g[0]["tr_dur"]})
        return _chain(ff, joined, fps, out, tmp_dir, tag + "_j", crf, preset)

    args = []
    for s in segs:
        args += ["-i", s["path"]]
    t0 = segs[0]["t_start"]
    lines = [f"[{i}:v]settb=AVTB,fps={fps},format=yuv420p,setpts=PTS-STARTPTS[s{i}]" for i in range(len(segs))]
    prev = "s0"
    for i in range(1, len(segs)):
        s = segs[i]
        lab = f"x{i}"
        if s["tr_dur"] <= 0 or s["tr_type"] == "cut":
            lines.append(f"[{prev}][s{i}]concat=n=2:v=1:a=0[{lab}]")
        else:
            offset = s["t_start"] - t0  # segment i starts (with its handle) exactly when the blend begins
            lines.append(f"[{prev}][s{i}]xfade=transition={s['tr_type']}:duration={s['tr_dur']:.4f}:"
                         f"offset={offset:.4f}[{lab}]")
        prev = lab
    script = tmp_dir / f"{tag}_graph.txt"
    script.write_text(";\n".join(lines), encoding="utf-8")
    tail = ["-map", f"[{prev}]", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-r", str(fps), out]
    try:
        ff.run(args + ["-filter_complex_script", str(script)] + tail)
    except RuntimeError as e:
        if "filter_complex_script" not in str(e).split("---")[-1]:
            raise
        ff.run(args + ["-/filter_complex", str(script)] + tail)   # ffmpeg 7.1+ spelling
    return out


def render_final(b) -> str:
    fps = b.canvas["fps"]
    tmp = b.work / "ffmpeg"
    tmp.mkdir(exist_ok=True)
    segs = []
    for c in b.clips:
        tr = c["cut"].get("transition_in") or {"type": "cut", "duration": 0}
        segs.append({"path": c["path"], "t_start": c["t_start"], "t_end": c["t_end"],
                     "tr_type": tr.get("type", "cut"), "tr_dur": float(tr.get("duration", 0))})
    log(f"  joining {len(segs)} clips with transitions")
    r = b.project["render"]
    video = _chain(b.ff, segs, fps, str(tmp / "video.mp4"), tmp, "v", int(r.get("final_crf", 18)),
                   r.get("final_preset", "medium"))

    name = b.project["name"]
    out = str(b.out_dir / f"{name}.mp4")
    a = b.project["audio"]
    vf = []
    cwd = None
    if b.project["subtitles"].get("burn_in") and b.ass:
        cwd = str(Path(b.ass).parent)       # relative name avoids Windows path escaping in filters
        vf = ["-vf", f"ass={Path(b.ass).name}"]
    args = ["-i", os.path.abspath(video), "-i", os.path.abspath(b.audio_wav)] + vf + [
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264" if vf else "copy", *(["-preset", r.get("final_preset", "medium"), "-crf", str(r.get("final_crf", 18)),
                                         "-pix_fmt", "yuv420p"] if vf else []),
        "-af", _loudnorm(b, a),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{b.plan['duration']:.3f}", "-movflags", "+faststart", os.path.abspath(out)]
    b.ff.run(args, cwd=cwd)
    log(f"  wrote {out}")
    return out
