"""Orchestrates a build: voice -> timing plan -> pictures -> cut clips -> audio -> captions -> outputs."""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from . import timing
from .audio_mix import Mixer
from .config import Settings
from .frames import render_job
from .imagegen import ImageGenerator
from .postprocess import PostProcessor
from .project import load_project, normalize
from .sfx import SFXResolver
from .styles import StyleBook
from .subtitles import build_captions, to_ass, to_srt
from .tts import synthesize
from .util import FFmpeg, log, read_json, stable_hash, write_json


class Build:
    """Everything produced for one project; passed to the output backends."""

    def __init__(self, project, styles, settings, ff):
        self.project = project
        self.styles = styles
        self.settings = settings
        self.ff = ff
        self.out_dir = Path(project["output_dir"])
        self.work = self.out_dir / "work"
        self.work.mkdir(parents=True, exist_ok=True)
        self.voices: dict = {}
        self.plan: dict = {}
        self.pools: dict[str, list[dict]] = {}       # pool id -> [{raw, processed, meta}]
        self.overlays: dict[str, dict] = {}          # scene id -> {bg, layers:{id:{base, pose_i}}}
        self.clips: list[dict] = []
        self.audio_wav: Optional[str] = None
        self.audio_events: list[dict] = []
        self.stems: dict = {}
        self.captions: list[dict] = []
        self.srt: Optional[str] = None
        self.ass: Optional[str] = None
        self.report: dict = {"warnings": []}

    @property
    def canvas(self):
        return self.project["canvas"]


def load(project_path: str, settings: Settings, preview: bool = False, styles_path: Optional[str] = None,
         offline: bool = False):
    import json
    with open(project_path, encoding="utf-8") as f:
        raw = json.load(f)
    if offline:  # no network: stand-in voice and pictures, to test timing/motion/sound quickly
        raw.setdefault("voice", {})["provider"] = "dummy"
        raw["image_provider"] = "placeholder"
        raw.setdefault("audio", {})["freesound"] = False
    styles = StyleBook.load(styles_path, raw.get("style_overrides"))
    project = normalize(raw, str(Path(project_path).resolve().parent), styles.names())
    if preview:
        c = project["canvas"]
        c["width"], c["height"] = c["width"] // 2 // 2 * 2, c["height"] // 2 // 2 * 2
        project["render"]["motion_blur_samples"] = min(4, project["render"]["motion_blur_samples"])
        project["render"]["final_preset"] = "veryfast"
        project["output_dir"] = project["output_dir"] + "_preview"
    if offline:
        project["output_dir"] = project["output_dir"] + "_offline"
    ff = FFmpeg(settings.ffmpeg_path, settings.ffprobe_path)
    return Build(project, styles, settings, ff)


# --------------------------------------------------------------------------- steps

def step_voice(b: Build):
    log("[1/7] Voiceover")
    for sc in b.project["scenes"]:
        cfg = dict(b.project["voice"], **(sc.get("voice") or {}))
        v = synthesize(sc, cfg, str(b.work / "voice"), b.ff, b.settings)
        if v:
            b.voices[sc["id"]] = v


def step_plan(b: Build):
    log("[2/7] Timing plan")
    b.plan = timing.build_plan(b.project, b.styles, b.voices)
    timing.quantize(b.plan, int(b.canvas["fps"]))
    for sid, notes in b.plan["notes"].items():
        for n in notes:
            log(f"  {sid}: {n}")
    from .popups import resolve
    for n in resolve(b.project, b.plan, b.voices):
        log(f"  {n}")
    write_json(b.work / "plan.json", b.plan)
    log(f"  {len(b.plan['cuts'])} cuts, total {b.plan['duration']:.1f}s")


def _gen_settings(b: Build, style_name: str) -> dict:
    g = dict(b.styles.get(style_name).get("generator", {}))
    if b.project.get("image_provider"):
        g["provider"] = b.project["image_provider"]
    return g


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def job_list(b: Build) -> list[dict]:
    """Every picture / cut-out / clip the plan needs, with a ready-to-paste prompt for Google Flow."""
    from . import cast as C
    jobs = []
    scenes = {s["id"]: s for s in b.project["scenes"]}
    # recurring characters first: the master picture of each, then its poses (made from the master)
    cast = b.project.get("cast") or {}
    default_style = b.project["default_style"]
    for name, poses in C.used_poses(b.project).items():
        member = cast[name]
        st = b.styles.get(member.get("style") or default_style)
        prefix = st.get("character_prefix") or st.get("prompt_prefix", "")
        key = C.key_for(member["look"], member.get("key"))
        where = [s["id"] for s in b.project["scenes"]
                 if any(l.get("cast") == name for l in (s.get("overlay") or {}).get("layers", []))]
        jobs.append({"id": C.job_id(name, "base"), "scene": ",".join(where), "kind": "cast", "cast": name,
                     "pose": "base", "key": key, "prompt": member.get("exact") or C.master_prompt(prefix, member, key),
                     "narration": f"master picture of '{name}' (used in {', '.join(where)})"})
        for pose in sorted(poses - {"base"}):
            jobs.append({"id": C.job_id(name, pose), "scene": ",".join(where), "kind": "cast_pose", "cast": name,
                         "pose": pose, "key": key, "reference": C.job_id(name, "base"),
                         "prompt": C.pose_prompt(prefix, member, pose, key),
                         "narration": f"'{name}' pose '{pose}' - attach {C.job_id(name, 'base')} as the reference"})
    for pool_id, pool in b.plan["pools"].items():
        sc = scenes[pool_id]
        style = sc["style"]
        nar = sc.get("voiceover", "")
        if pool.get("clip"):
            continue
        if pool.get("overlay"):
            ov = sc["overlay"]
            bg = ov.get("background") or {"prompt": sc.get("visual") or nar}
            if not bg.get("path"):
                jobs.append({"id": f"{pool_id}_bg", "scene": pool_id, "kind": "background",
                             "prompt": bg.get("exact") or b.styles.background_prompt(style, bg["prompt"]), "narration": nar})
            for layer in ov["layers"]:
                if layer.get("cast"):
                    continue
                kind = layer.get("kind", "character")
                for slot, entry in [("", layer["image"])] + [(f"_pose{i + 1}", p["image"]) for i, p in enumerate(layer["poses"])]:
                    if not entry.get("path"):
                        jobs.append({"id": f"{pool_id}_{layer['id']}{slot}", "scene": pool_id, "kind": kind,
                                     "prompt": entry.get("exact") or b.styles.layer_prompt(style, entry["prompt"], kind),
                                     "narration": nar})
            continue
        entries = sc["images"][: pool["count"]] if sc.get("images") else [{"prompt": sc["visual"]}] * pool["count"]
        shots = b.styles.get(style).get("shot_variants") or [None]
        for k, entry in enumerate(entries):
            if entry.get("path"):
                continue
            shot = entry.get("shot") or (shots[k % len(shots)] if pool["count"] > 1 else None)
            jobs.append({"id": f"{pool_id}_{k + 1}", "scene": pool_id, "kind": "scene",
                         "prompt": entry.get("exact") or b.styles.scene_prompt(style, entry["prompt"], shot), "narration": nar})
    for j in jobs:
        j.setdefault("file", str(Path(b.project["base_dir"]) / "images" / f"{j['id']}.png"))
        j["file"] = os.path.relpath(j["file"], b.project["base_dir"]).replace("\\", "/")
    return jobs


def write_image_jobs(b: Build, reset: bool = False) -> str:
    """image_jobs.json (machine readable) + image_prompts.md (to read). Edited prompts survive re-planning."""
    base = Path(b.project["base_dir"])
    (base / "images").mkdir(exist_ok=True)
    path = base / "image_jobs.json"
    old = {}
    if path.exists() and not reset:
        try:
            old = {j["id"]: j for j in read_json(path)}
        except Exception:
            old = {}
    jobs = job_list(b)
    for j in jobs:
        j["auto_prompt"] = j["prompt"]
        o = old.get(j["id"])
        # keep a prompt someone edited by hand (it differs from what the engine wrote last time)
        if o and o.get("prompt") and o["prompt"] != o.get("auto_prompt", o["prompt"] if "auto_prompt" in o else None):
            j["prompt"] = o["prompt"]
            j["edited"] = True
        j["done"] = bool(find_file(base, j))
    write_json(path, jobs)
    lines = [f"# Image prompts for {b.project['name']}", "",
             f"{sum(1 for j in jobs if not j['done'])} of {len(jobs)} still to make. Save each result as the file named.", ""]
    for j in jobs:
        lines += [f"## {j['id']}  ({j['kind']}){'  - done' if j['done'] else ''}", f"File: `{j['file']}`", "",
                  f"Narration: {j['narration']}", "", "```", j["prompt"], "```", ""]
    (base / "image_prompts.md").write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def find_file(base: Path, job: dict) -> Optional[str]:
    p = base / job["file"]
    if p.exists():
        return str(p)
    if job.get("kind") != "video":
        for ext in IMG_EXT:
            q = p.with_suffix(ext)
            if q.exists():
                return str(q)
    return None


def step_images(b: Build):
    log("[3/7] Pictures")
    gen = ImageGenerator(b.settings.cache_dir, b.settings.hf_token)
    post = PostProcessor(b.settings.cache_dir, b.canvas, b.settings.realesrgan_path,
                         float(b.project.get("corner_crop", 0.08)))
    seed0 = int(b.project.get("seed", 0))
    scenes = {s["id"]: s for s in b.project["scenes"]}
    base = Path(b.project["base_dir"])
    jobs = {j["id"]: j for j in job_list(b)}
    jp = base / "image_jobs.json"
    if jp.exists():   # use the (possibly edited) prompts/file names from the plan
        for j in read_json(jp):
            if j["id"] in jobs:
                jobs[j["id"]].update({k: j[k] for k in ("file", "prompt") if k in j})
    missing: list[str] = []

    for pool_id, pool in b.plan["pools"].items():
        sc = scenes[pool_id]
        style_name = sc["style"]
        st = b.styles.get(style_name)
        g = _gen_settings(b, style_name)
        base_seed = int(g.get("seed", 0)) + seed0 + sc["index"] * 101

        def make(entry: dict, j: int, kind: str = "scene", subject: Optional[str] = None, job_id: str = "") -> dict:
            if entry.get("path") and os.path.exists(entry["path"]):
                meta = gen.from_file(entry["path"], style_name, kind)
            elif g.get("provider") == "flow" and job_id in jobs and find_file(base, jobs[job_id]):
                meta = gen.from_file(find_file(base, jobs[job_id]), style_name, kind)
            else:
                if g.get("provider") == "flow":
                    missing.append(job_id or entry.get("path", "?"))
                    g_local = dict(g, provider="placeholder")
                else:
                    g_local = g
                subj = subject or entry.get("prompt") or sc.get("visual") or ""
                if kind == "scene":
                    shots = st.get("shot_variants") or [None]
                    shot = entry.get("shot") or (shots[j % len(shots)] if not entry.get("exact") else None)
                    prompt = b.styles.scene_prompt(style_name, subj, shot) if not entry.get("exact") else subj
                else:
                    prompt = b.styles.layer_prompt(style_name, subj, kind) if not entry.get("exact") else subj
                gw, gh = int(g.get("width", 1024)), int(g.get("height", 576))
                if kind == "character":      # standing figures: portrait frame
                    gw, gh = min(gw, gh), max(gw, gh)
                elif kind == "prop":
                    gw = gh = (min(gw, gh) + max(gw, gh)) // 2 // 64 * 64
                meta = gen.generate({"style": style_name, "kind": kind, "prompt": prompt, "subject": subj,
                                     "seed": int(entry.get("seed", base_seed + j * 17)),
                                     "width": gw, "height": gh,
                                     "provider": g_local.get("provider", "placeholder"), "model": g_local.get("model"),
                                     "steps": g_local.get("steps", 4)})
            if meta.get("fallback"):
                b.report["warnings"].append(f"{sc['id']}: placeholder used ({meta.get('error')})")
            return meta

        if pool.get("overlay"):
            ov = sc["overlay"]
            bg_entry = ov.get("background") or {"prompt": sc.get("visual") or sc["voiceover"]}
            bg_meta = make(bg_entry, 0, job_id=f"{pool_id}_bg")
            layers = {}
            for li, layer in enumerate(ov["layers"]):
                lstyle = layer.get("style", style_name)
                method = layer.get("cutout") or b.styles.get(lstyle).get("cutout", "auto")
                imgs = {}
                if layer.get("cast"):
                    from . import cast as C
                    base_pose = layer.get("pose") or "base"
                    for pose in [base_pose] + sorted(C.layer_poses(layer) - {base_pose}):
                        jid = C.job_id(layer["cast"], pose)
                        m = make({"prompt": b.project["cast"][layer["cast"]]["look"]}, 50 + li * 7 + len(imgs),
                                 kind="character", job_id=jid)
                        cut = post.cutout(m["path"], method)
                        imgs["base" if pose == base_pose else "f:" + pose] = cut
                    layers[layer["id"]] = imgs
                    continue
                for slot, entry in [("base", layer["image"])] + [(f"pose_{i}", p["image"])
                                                                  for i, p in enumerate(layer["poses"])]:
                    jid = f"{pool_id}_{layer['id']}" + ("" if slot == "base" else f"_pose{int(slot.split('_')[1]) + 1}")
                    m = make(entry, 50 + li * 7 + len(imgs), kind=layer.get("kind", "character"), job_id=jid)
                    imgs[slot] = post.cutout(m["path"], method)
                layers[layer["id"]] = imgs
            b.overlays[sc["id"]] = {"bg": post.scene_image(bg_meta["path"], style_name, st), "layers": layers,
                                    "bg_raw": bg_meta["path"]}
            b.pools[pool_id] = [{"raw": bg_meta["path"], "processed": b.overlays[sc["id"]]["bg"], "meta": bg_meta}]
            continue

        if pool.get("clip"):
            b.pools[pool_id] = [{"raw": sc["clip"], "processed": sc["clip"], "meta": {}}]
            if not os.path.exists(sc["clip"]):
                raise RuntimeError(f"Scene {pool_id}: clip not found: {sc['clip']}")
            continue
        if sc.get("images"):
            entries = sc["images"][: pool["count"]]
        else:
            entries = [{"prompt": sc["visual"]} for _ in range(pool["count"])]
        items = []
        for j, entry in enumerate(entries):
            meta = make(entry, j, job_id=f"{pool_id}_{j + 1}")
            items.append({"raw": meta["path"], "processed": post.scene_image(meta["path"], style_name, st),
                          "meta": meta})
        b.pools[pool_id] = items
        log(f"  {pool_id}: {len(items)} picture(s), style {style_name}")
    b.report["images"] = gen.report
    if missing:
        msg = f"{len(missing)} picture(s) not made yet, placeholders used: {', '.join(missing[:12])}" + (" ..." if len(missing) > 12 else "")
        log("  " + msg)
        b.report["warnings"].append(msg)


def step_clips(b: Build):
    log("[4/7] Rendering cut clips")
    c = b.canvas
    w, h, fps = c["width"], c["height"], c["fps"]
    cuts = b.plan["cuts"]
    clip_dir = b.work / "clips"
    clip_dir.mkdir(exist_ok=True)
    scenes = {s["id"]: s for s in b.project["scenes"]}
    windows = {wdw["id"]: wdw for wdw in b.plan["scenes"]}
    jobs = []
    t0 = time.time()
    for i, cut in enumerate(cuts):
        td_in = cut["transition_in"]["duration"] if cut["transition_in"] else 0.0
        td_out = cuts[i + 1]["transition_in"]["duration"] if i + 1 < len(cuts) and cuts[i + 1]["transition_in"] else 0.0
        t_start, t_end = cut["start"] - td_in / 2, cut["end"] + td_out / 2
        st = b.styles.get(cut["style"])
        sc = scenes[cut["scene_id"]]
        overlay_spec = sc.get("overlay") if cut["kind"] == "overlay" else None
        presets = st.get("motion", {}).get("presets") or ["none"]
        preset = (overlay_spec.get("background_motion", "push_in") if overlay_spec
                  else cut.get("motion") or presets[cut["motion_idx"] % len(presets)])
        pool = b.pools[cut["pool"]]
        item = pool[cut["image"] % len(pool)]
        if cut["kind"] == "clip":
            out = clip_dir / f"cut_{i + 1:03d}_{stable_hash('vclip-v1', sc['clip'], os.path.getmtime(sc['clip']), round(t_end - t_start, 3), w, h, fps, sc.get('clip_crop', 0.0))}.mp4"
            if not out.exists():
                _render_video_clip(b, sc["clip"], str(out), t_end - t_start, float(sc.get("clip_crop", 0.0)))
            b.clips.append({"cut": cut, "path": str(out), "t_start": t_start, "t_end": t_end,
                            "handle_in": td_in / 2, "handle_out": td_out / 2, "preset": "clip",
                            "image": None, "raw_image": sc["clip"]})
            continue
        layer_images = b.overlays.get(cut["scene_id"], {}).get("layers") if overlay_spec else None
        key = stable_hash("clip-v3", item["processed"], preset, cut["variant"], round(t_start, 3), round(t_end, 3),
                          w, h, fps, st.get("frame_fx"), st.get("motion"), st.get("post", {}).get("paper"),
                          b.project["render"], overlay_spec, layer_images, windows[cut["scene_id"]]["start"])
        out = clip_dir / f"cut_{i + 1:03d}_{key}.mp4"
        if not out.exists():
            jobs.append({"ffmpeg": b.ff.ffmpeg, "out": str(out), "tmp": str(out) + ".part.mp4", "w": w, "h": h,
                         "fps": fps, "t_start": t_start, "t_end": t_end,
                         "scene_start": windows[cut["scene_id"]]["start"], "image": item["processed"],
                         "style": st, "preset": preset, "variant": cut["variant"],
                         "key": f"{cut['pool']}:{cut['image']}", "overlay": overlay_spec,
                         "layer_images": layer_images, "render": b.project["render"],
                         "label": f"cut {i + 1}/{len(cuts)} {cut['scene_id']} {cut['kind']} {preset} "
                                  f"{t_end - t_start:.2f}s"})
        b.clips.append({"cut": cut, "path": str(out), "t_start": t_start, "t_end": t_end,
                        "handle_in": td_in / 2, "handle_out": td_out / 2, "preset": preset,
                        "image": item["processed"], "raw_image": item["raw"]})
    if not jobs:
        log("  all clips cached")
        return
    workers = int(b.project["render"].get("workers") or max(1, min(6, (os.cpu_count() or 2) - 1)))
    # overlay clips are the slowest: start them first
    jobs.sort(key=lambda j: (j["overlay"] is None, -(j["t_end"] - j["t_start"])))
    log(f"  rendering {len(jobs)} clip(s) with {workers} worker(s)")
    if workers <= 1:
        for j in jobs:
            render_job(j)
            log(f"  {j['label']} ({time.time() - t0:.0f}s)")
        return
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(render_job, j): j for j in jobs}
        for done, f in enumerate(as_completed(futs), 1):
            f.result()
            log(f"  [{done}/{len(jobs)}] {futs[f]['label']} ({time.time() - t0:.0f}s)")


def _render_video_clip(b: Build, src: str, out: str, length: float, crop: float = 0.0):
    """A generated video clip (e.g. Veo from Google Flow) fitted to the cut: cover-scaled to the canvas,
    looped or slowed if it is shorter than the cut, trimmed if longer. `crop` (e.g. 0.04) zooms in a
    little, which hides a corner watermark."""
    c = b.canvas
    w, h, fps = c["width"], c["height"], c["fps"]
    src_len = max(0.1, b.ff.duration(src))
    speed = ""
    loop = []
    if src_len < length:
        if length / src_len <= 1.35:          # slightly short: slow it down a touch instead of a visible loop
            speed = f"setpts={length / src_len:.4f}*PTS,"
        else:
            loop = ["-stream_loop", "-1"]
    z = 1.0 + max(0.0, crop)
    vf = (f"{speed}scale={int(w * z)}:{int(h * z)}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={w}:{h},fps={fps},format=yuv420p")
    r = b.project["render"]
    b.ff.run(loop + ["-i", src, "-t", f"{length:.3f}", "-vf", vf, "-an", "-c:v", "libx264",
                     "-preset", r.get("preset", "medium"), "-crf", str(r.get("crf", 18)), "-pix_fmt", "yuv420p",
                     "-r", str(fps), "-movflags", "+faststart", out])


def _has_audio(path: str, ff) -> bool:
    import json as _j
    import subprocess
    try:
        o = subprocess.run([ff.ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                            "-of", "json", path], capture_output=True, text=True, timeout=60)
        return bool(_j.loads(o.stdout or "{}").get("streams"))
    except Exception:
        return False


def _sound_len(path: str, ff) -> float:
    try:
        return ff.duration(path)
    except Exception:
        return 0.5


def step_audio(b: Build):
    log("[5/7] Audio mix")
    a = b.project["audio"]
    total = b.plan["duration"]
    mix = Mixer(total, b.ff)
    sfx = SFXResolver(b.settings.sfx_library_dir, b.settings.cache_dir, b.settings.freesound_api_key,
                      bool(a.get("freesound")), a.get("sfx_source", "auto"))
    windows = {wdw["id"]: wdw for wdw in b.plan["scenes"]}
    scenes = {s["id"]: s for s in b.project["scenes"]}

    for sid, v in b.voices.items():
        mix.place("voice", v["path"], windows[sid]["voice_start"], a["voice_gain_db"], label=f"voice {sid}")

    from . import events as EV
    from .popups import find_phrase
    from .sfx_lib import LEVELS
    placed: list[tuple[float, str]] = []

    def add_sfx(name, at, gain=0.0, center=False, label=""):
        # the same sound twice within 0.2 s sounds like a glitch: skip it
        if any(n == name and abs(t - at) < 0.2 for t, n in placed):
            return
        path = sfx.resolve(name, seed=int(at * 10))
        if not path:
            return
        if center:
            at = at - min(_sound_len(path, b.ff), 1.2) / 2
        placed.append((at, name))
        mix.place("sfx", path, at, a["sfx_gain_db"] + LEVELS.get(name, 0.0) + gain, label=label or name)

    def word_time(sid, cue, after=0.0):
        """Scene-relative seconds for a cue: a number, or a word/phrase from the scene's voiceover."""
        if cue is None:
            return None
        if isinstance(cue, (int, float)):
            return float(cue)
        v = b.voices.get(sid)
        if not v:
            return None
        t = find_phrase(v["words"], str(cue), after)
        return None if t is None else (windows[sid]["voice_start"] - windows[sid]["start"]) + t

    trans = a.get("transition_sfx", "auto")      # "auto" (style's sound) | "none" | a sound name
    if a.get("auto_sfx", True) and trans != "none":
        for cut in b.plan["cuts"]:
            tr = cut.get("transition_in")
            if not tr:
                continue
            st = b.styles.get(cut["style"]).get("sfx", {})
            name = st.get("cut_transition") if tr["kind"] == "cut" else st.get("scene_transition")
            if trans not in ("auto", None) and tr["kind"] != "cut":
                name = trans
            if name:
                add_sfx(name, cut["start"], float(a.get("transition_gain_db", 0.0)), center=True,
                        label=f"{tr['kind']} transition")
        for sid, ov in ((s["id"], s["overlay"]) for s in b.project["scenes"] if s.get("overlay")):
            st = b.styles.get(scenes[sid]["style"]).get("sfx", {})
            start = windows[sid]["start"]
            for layer in ov["layers"]:
                if layer.get("auto_sfx", True) is False:
                    continue
                for ka, kb in zip(layer["keyframes"], layer["keyframes"][1:]):
                    dist = abs(kb.get("x", ka.get("x", 0)) - ka.get("x", 0)) + abs(kb.get("y", ka.get("y", 0)) - ka.get("y", 0))
                    if dist >= 0.15:
                        if st.get("overlay_enter"):
                            add_sfx(st["overlay_enter"], start + ka["t"], label=f"{layer['id']} moves")
                        if st.get("overlay_land"):
                            add_sfx(st["overlay_land"], start + kb["t"] - 0.05, -2, label=f"{layer['id']} lands")
            for fx in ov.get("fx", []):
                if fx.get("sfx"):
                    add_sfx(fx["sfx"], start + fx["t"], label=f"fx {fx['type']}")
    for sc in b.project["scenes"]:
        win = windows[sc["id"]]
        explicit = set()
        for s in sc.get("sfx", []):
            rel = word_time(sc["id"], s.get("at"))
            at = win["start"] + (rel if rel is not None else 0.2)
            explicit.add(s.get("name"))
            add_sfx(s.get("path") or s["name"], at, float(s.get("gain_db", 0)), label=s.get("name", "sfx"))
        # sounds for what the narration describes ("the crowd cheered" -> cheer under "cheered")
        if a.get("auto_events", True) and sc.get("auto_sfx", True) and sc["id"] in b.voices:
            for t, name, word in EV.find_events(b.voices[sc["id"]]["words"], int(a.get("max_events_per_scene", 2))):
                if name in explicit:
                    continue
                add_sfx(name, win["voice_start"] + t - 0.05, float(a.get("event_gain_db", 0.0)), label=f"event {name} ({word})")
        amb_name = sc.get("ambience")
        if not amb_name and a.get("auto_ambience", True) and sc.get("auto_sfx", True):
            amb_name = EV.pick_ambience(" ".join([sc.get("voiceover") or "", sc.get("visual") or ""]))
        if amb_name:
            sc["_ambience_used"] = amb_name
            length = win["end"] - win["start"] + 1.0
            path = sfx.resolve(amb_name, seed=sc["index"], duration=length)
            if path:
                mix.place("amb", path, max(0, win["start"] - 0.5), a["ambience_gain_db"], length=length + 0.5,
                          loop=True, fade_in=0.8, fade_out=1.0, label=f"ambience {amb_name}")
    # sound that came with generated video clips (Veo makes its own ambience / sfx)
    for cl in b.clips:
        sc = scenes[cl["cut"]["scene_id"]]
        if cl["cut"]["kind"] == "clip" and sc.get("clip_audio", True) and _has_audio(sc["clip"], b.ff):
            mix.place("amb", sc["clip"], cl["t_start"], float(sc.get("clip_volume_db", -14.0)),
                      length=cl["t_end"] - cl["t_start"], fade_in=0.3, fade_out=0.4, label=f"clip audio {sc['id']}")
    music = a.get("music")
    if music == "auto":
        import hashlib
        import soundfile as sf
        from . import story as ST
        from .music import music_track, canon
        order = [wdw["id"] for wdw in b.plan["scenes"]]
        fixed = a.get("music_mood", "auto")
        if fixed and fixed != "auto":
            kind, moods = canon(fixed), [canon(fixed)] * len(order)      # one style for the whole video
        else:
            kind, moods = ST.scene_moods([scenes[i] for i in order], b.project.get("story_type"))
        secs = [(windows[i]["start"], windows[i]["end"], canon(m)) for i, m in zip(order, moods)]
        secs = ST.smooth(secs) if len(set(moods)) > 1 else secs
        b.story_kind, b.music_sections = kind, secs
        log(f"  story type: {kind}; music: " + " -> ".join(f"{m} ({st:.0f}-{en:.0f}s)" for st, en, m in secs))
        key = hashlib.sha1(repr((secs, int(total))).encode()).hexdigest()[:10]
        music = str(b.work / f"music_{key}.wav")
        if not os.path.exists(music):
            sf.write(music, music_track(secs, total + 1.0, seed=int(b.project.get("seed", 0))), 48000)
    if music:
        mix.place("music", music, 0.0, a["music_gain_db"], length=total, loop=True, fade_in=1.5,
                  fade_out=3.0, label="music")
    raw = str(b.work / "mix_raw.wav")
    mix.render(raw, a["duck_db"])
    b.audio_wav = raw
    b.audio_events = mix.events
    b.stems = mix.write_stems(str(b.work / "stems"))
    credits = [c for c in (sfx.credit_for(e["path"]) for e in mix.events if e["bus"] == "sfx" or e["bus"] == "amb") if c]
    if credits:
        uniq = {c["url"]: c for c in credits}.values()
        lines = [f"\"{c['name']}\" by {c['author']} ({c['license']}) {c['url']}" for c in uniq]
        (b.out_dir / "SOUND_CREDITS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"  wrote SOUND_CREDITS.txt ({len(lines)} Freesound credits - include in your video description)")


def step_captions(b: Build):
    log("[6/7] Captions")
    if not b.project["subtitles"].get("enabled", True):
        return
    windows = {wdw["id"]: wdw for wdw in b.plan["scenes"]}
    data = [(s["id"], s["style"], windows[s["id"]]["voice_start"], b.voices[s["id"]]["words"])
            for s in b.project["scenes"] if s["id"] in b.voices]
    sub = b.project["subtitles"]
    b.captions = build_captions(data, sub.get("max_words", 7), sub.get("max_chars", 42))
    name = b.project["name"]
    b.srt = str(b.out_dir / f"{name}.srt")
    Path(b.srt).write_text(to_srt(b.captions), encoding="utf-8")
    b.ass = str(b.work / f"{name}.ass")
    Path(b.ass).write_text(to_ass(b.captions, b.styles, b.canvas["width"], b.canvas["height"]), encoding="utf-8")


def step_outputs(b: Build, only: Optional[list[str]] = None):
    log("[7/7] Outputs")
    outputs = only or b.project["outputs"]
    results = {}
    for o in outputs:
        if o == "ffmpeg":
            from .backends.ffmpeg_backend import render_final
            results["mp4"] = render_final(b)
    return results


def run(project_path: str, settings: Settings, preview: bool = False, plan_only: bool = False,
        only: Optional[list[str]] = None, styles_path: Optional[str] = None, offline: bool = False) -> dict:
    b = load(project_path, settings, preview, styles_path, offline)
    log(f"Project '{b.project['name']}' -> {b.out_dir}")
    if not plan_only:
        for sc in b.project["scenes"]:
            if sc.get("clip") and not os.path.exists(sc["clip"]):
                msg = f"{sc['id']}: video clip {os.path.basename(sc['clip'])} not found - using still pictures instead"
                log("  " + msg)
                b.report["warnings"].append(msg)
                sc["clip"] = None
                sc["visual"] = sc.get("visual") or sc.get("clip_prompt") or sc["voiceover"]
    step_voice(b)
    step_plan(b)
    if plan_only:
        jobs = write_image_jobs(b)
        return {"plan": str(b.work / "plan.json"), "image_jobs": jobs, "build": b}
    step_images(b)
    step_clips(b)
    step_audio(b)
    step_captions(b)
    results = step_outputs(b, only)
    report = {"project": b.project["name"], "duration": b.plan["duration"], "cuts": len(b.plan["cuts"]),
              "outputs": results, "warnings": b.report["warnings"], "notes": b.plan["notes"]}
    write_json(b.out_dir / "report.json", report)
    log("Done.")
    for k, v in results.items():
        log(f"  {k}: {v}")
    if b.report["warnings"]:
        log(f"  {len(b.report['warnings'])} warning(s) - see report.json")
    results["build"] = b
    return results
