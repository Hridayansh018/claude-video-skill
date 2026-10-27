"""Command line (run from the claude-video-skill folder):

  python -m vdo new  script.md  [--name greece] [--scenes 1-5] [--style stickman] [--image-duration 6]
  python -m vdo plan projects/greece/project.json     # voice + timing + image_prompts.md / image_jobs.json
  python -m vdo status projects/greece/project.json   # which pictures are still missing
  python -m vdo import projects/greece/project.json   # move Flow downloads (vdo__greece__<id>.jpg) into images/
  python -m vdo sheet  projects/greece/project.json   # contact_sheet.jpg of every picture
  python -m vdo build projects/greece/project.json [--preview] [--allow-missing]
  python -m vdo doctor                                # check ffmpeg, voice model, packages
  python -m vdo sfx-list
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .config import REPO_ROOT, load_settings
from .util import log, read_json, write_json


def _parse_scene_list(s: str) -> list[int]:
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def cmd_new(args):
    from .project import safe_name
    from .script_parser import build_project
    src = Path(args.script)
    text = src.read_text(encoding="utf-8")
    name = safe_name(args.name or src.stem)
    pdir = Path(args.projects_dir or REPO_ROOT / "projects") / name
    if (pdir / "project.json").exists() and not args.force:
        log(f"{pdir / 'project.json'} already exists (use --force to replace it).")
        sys.exit(1)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "images").mkdir(exist_ok=True)
    (pdir / "clips").mkdir(exist_ok=True)
    if src.resolve() != (pdir / "script.md").resolve():
        shutil.copyfile(src, pdir / "script.md")
    style_map = {n: s for flag, s in ((args.stickman, "stickman"), (args.oil, "oil")) for n in _parse_scene_list(flag)}
    rng = None
    if args.scenes:
        nums = _parse_scene_list(args.scenes)
        rng = (min(nums), max(nums))
    proj = build_project(text, name, default_style=args.style, style_map=style_map,
                         image_duration=args.image_duration, scene_range=rng, use_anchor=args.use_anchor)
    if args.voice:
        proj["voice"] = {"provider": args.voice}
    if args.no_script_timing:
        proj["timing"] = {"duration_mode": "voice"}
    write_json(pdir / "project.json", proj)
    log(f"Created {pdir / 'project.json'} with {len(proj['scenes'])} scenes.")
    log(f"Next: python -m vdo plan \"{pdir / 'project.json'}\"")


def _print_plan(b, res):
    log("")
    log(f"{'#':>3} {'scene':<6} {'style':<9} {'kind':<8} {'start':>7} {'end':>7} {'hold':>5}  pic  transition-in")
    for i, c in enumerate(b.plan["cuts"], 1):
        tr = c["transition_in"]
        trs = f"{tr['type']} {tr['duration']:.2f}s ({tr['kind']})" if tr else "-"
        log(f"{i:>3} {c['scene_id']:<6} {c['style']:<9} {c['kind']:<8} {c['start']:>7.2f} {c['end']:>7.2f} "
            f"{c['end'] - c['start']:>5.2f}  {c['image']}{'v' + str(c['variant']) if c['variant'] else '  '}  {trs}")
    log(f"Total {b.plan['duration']:.2f}s, {len(b.plan['cuts'])} cuts.")


def cmd_plan(args):
    from .pipeline import run
    res = run(args.project, load_settings(args.config), plan_only=True, styles_path=args.styles, offline=args.offline)
    b = res["build"]
    _print_plan(b, res)
    if args.reset_prompts:
        from .pipeline import write_image_jobs
        write_image_jobs(b, reset=True)
    jobs = read_json(res["image_jobs"])
    todo = [j for j in jobs if not j["done"]]
    log(f"{len(jobs)} picture/clip jobs, {len(todo)} still to make.")
    log(f"Prompts: {Path(res['image_jobs']).with_name('image_prompts.md')}")
    log(f"Jobs:    {res['image_jobs']}")


def cmd_status(args):
    from .pipeline import find_file
    proj = Path(args.project)
    jp = proj.parent / "image_jobs.json"
    if not jp.exists():
        log("No image_jobs.json yet - run plan first.")
        sys.exit(1)
    jobs = read_json(jp)
    missing = [j for j in jobs if not find_file(proj.parent, j)]
    log(f"{len(jobs) - len(missing)} of {len(jobs)} ready.")
    for j in missing:
        log(f"  missing {j['id']:<22} {j['kind']:<10} -> {j['file']}")
    if args.json:
        print(json.dumps([j["id"] for j in missing]))


def cmd_import(args):
    from . import flow_import
    proj = Path(args.project)
    pdir = proj.parent
    name = read_json(proj).get("name") or pdir.name
    if args.chunks:
        got = flow_import.from_chunks(pdir, args.chunks)
    else:
        got = flow_import.from_downloads(pdir, name, args.downloads)
    log(f"Imported {len(got)} picture(s): {', '.join(got) if got else '-'}")
    if got:
        log(f"Contact sheet: {flow_import.contact_sheet(pdir)}")


def cmd_sheet(args):
    from . import flow_import
    log(flow_import.contact_sheet(Path(args.project).parent))


def cmd_build(args):
    from .pipeline import find_file, run
    proj = Path(args.project)
    jp = proj.parent / "image_jobs.json"
    if jp.exists() and not args.allow_missing and not args.offline:
        missing = [j["id"] for j in read_json(jp) if j["kind"] != "video" and not find_file(proj.parent, j)]
        if missing:
            log(f"{len(missing)} picture(s) still missing: {', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}")
            log("Make them first (see image_prompts.md), or add --allow-missing to use placeholders.")
            sys.exit(2)
    run(args.project, load_settings(args.config), preview=args.preview, styles_path=args.styles, offline=args.offline,
        overrides={"resolution": args.res, "captions": args.captions})


def cmd_chapters(args):
    """YouTube chapter lines from the final scene timings (output/work/plan.json). Rename them in the description."""
    proj = Path(args.project)
    project = read_json(proj)
    out_dir = proj.parent / project.get("output_dir", "output")
    plan_path = out_dir / "work" / "plan.json"
    if not plan_path.exists():
        log("No plan yet - build the video first.")
        sys.exit(1)
    plan = read_json(plan_path)
    scenes = {sc["id"]: sc for sc in project["scenes"]}
    rows = []
    for w in plan["scenes"]:
        sc = scenes.get(w["id"], {})
        title = sc.get("chapter") or " ".join((sc.get("voiceover") or w["id"]).split()[:6]).rstrip(".,;:")
        rows.append([w["start"], title])
    merged = []                                  # YouTube needs chapters of at least 10 s, the first at 0:00
    for t, title in rows:
        if merged and t - merged[-1][0] < 10:
            continue
        merged.append([t, title])
    if merged:
        merged[0][0] = 0.0
    lines = [f"{int(t) // 60}:{int(t) % 60:02d} {title}" for t, title in merged]
    (out_dir / "chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("\n".join(lines))
    log(f"wrote {out_dir / 'chapters.txt'}")


def cmd_sfx_list(args):
    from . import sfx_net
    from .sfx_lib import BEDS, ONE_SHOTS
    s = load_settings(args.config)
    log("Real recorded sounds (SFXMint, CC0, free, no account): " + ", ".join(sorted(sfx_net.ONE_SHOTS)))
    log("Real ambience beds: " + ", ".join(sorted(sfx_net.BEDS)))
    log("Generated sounds (made in code, used when no recording exists): " + ", ".join(sorted(ONE_SHOTS)))
    log("Generated beds: " + ", ".join(sorted(BEDS)) + "   (crowd / market / battle beds contain voices: only used if you ask)")
    log("Any folder sfx_library/<name>/ with your own .wav/.mp3 files overrides all of the above for that name.")
    lib = Path(s.sfx_library_dir)
    names = sorted(p.name for p in lib.iterdir() if p.is_dir() and not p.name.startswith("_")) if lib.exists() else []
    log(f"Your library ({lib}): " + (", ".join(names) if names else "(empty)"))


def cmd_voices(args) -> None:
    from .voices import make_samples, write_index
    from .config import REPO_ROOT
    from .util import find_binary
    s = load_settings(args.config)
    out = str(REPO_ROOT / "voices")
    done = make_samples(s, out, find_binary("ffmpeg", getattr(s, "ffmpeg_path", None)))
    write_index(out, done)
    print(f"{len(done)} voice samples in {out} (open voices/index.html to listen)")


def cmd_sfx_fetch(args):
    from . import sfx_net
    s = load_settings(args.config)
    have, want = sfx_net.prefetch(s.sfx_library_dir)
    log(f"SFXMint pack: {have} of {want} sounds available in {Path(s.sfx_library_dir) / '_sfxmint'}")
    if have < want:
        log("Some could not be downloaded (offline?). The engine uses its generated sounds for those.")


def cmd_doctor(args):
    s = load_settings(args.config)
    ok = True
    from .util import FFmpeg
    try:
        ff = FFmpeg(s.ffmpeg_path, s.ffprobe_path)
        log(f"[ok] ffmpeg: {ff.ffmpeg}")
        log(f"[{'ok' if ff.ffprobe else '--'}] ffprobe: {ff.ffprobe or 'not found (durations read via ffmpeg)'}")
    except Exception as e:
        ok = False
        log(f"[!!] ffmpeg: MISSING - {e}")
    for mod, why, required in (("numpy", "maths", True), ("PIL", "pictures (pillow)", True),
                               ("scipy", "sound effects", True), ("soundfile", "voice/music files", True),
                               ("kokoro_onnx", "offline voice (Kokoro)", True), ("edge_tts", "online voice (optional)", False),
                               ("rembg", "better cut-outs (optional)", False)):
        try:
            __import__(mod)
            log(f"[ok] {mod}: {why}")
        except Exception:
            log(f"[{'!!' if required else '--'}] {mod}: not installed ({why})")
            ok = ok and not required
    for label, path in (("Kokoro model", s.kokoro_model), ("Kokoro voices", s.kokoro_voices)):
        exists = Path(path).exists()
        log(f"[{'ok' if exists else '!!'}] {label}: {path}{'' if exists else '  (missing - see INSTALL.md)'}")
        ok = ok and exists
    log("Everything needed is installed." if ok else "Something is missing - see the [!!] lines and INSTALL.md.")
    sys.exit(0 if ok else 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="vdo", description="Paste a script, get a video.")
    p.add_argument("--config", help="config.json path (default: claude-video-skill/config.json)")
    p.add_argument("--styles", help="styles.json path (default: vdo/styles.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="create a project from a script file")
    n.add_argument("script")
    n.add_argument("--name", help="project name (default: script file name)")
    n.add_argument("--projects-dir", help="where projects live (default: claude-video-skill/projects)")
    n.add_argument("--style", default="stickman", help="style for every scene (stickman, oil)")
    n.add_argument("--stickman", default="", help="scene numbers forced to stickman, e.g. 10,24-25")
    n.add_argument("--oil", default="", help="scene numbers forced to oil painting")
    n.add_argument("--scenes", default="", help="only these scene numbers, e.g. 1-5")
    n.add_argument("--image-duration", type=float, default=6.0, help="preferred seconds per picture")
    n.add_argument("--use-anchor", action="store_true", help="use the script's Master Style Anchor as the style text")
    n.add_argument("--no-script-timing", action="store_true", help="ignore scene timestamps, follow the voice")
    n.add_argument("--voice", help="voice provider: kokoro (default), edge, dummy")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)

    pl = sub.add_parser("plan", help="voice + timing + picture prompts (no rendering)")
    pl.add_argument("project")
    pl.add_argument("--offline", action="store_true", help="estimate timings without voicing (fast)")
    pl.add_argument("--reset-prompts", action="store_true", help="discard edited prompts and rebuild them")
    pl.set_defaults(func=cmd_plan)

    stt = sub.add_parser("status", help="list pictures still missing")
    stt.add_argument("project")
    stt.add_argument("--json", action="store_true")
    stt.set_defaults(func=cmd_status)

    im = sub.add_parser("import", help="bring Google Flow pictures into the project")
    im.add_argument("project")
    im.add_argument("--downloads", help="folder the browser saved to (default: ~/Downloads)")
    im.add_argument("--chunks", nargs="+", help="text files holding vdo.chunk(i) output (remote sessions)")
    im.set_defaults(func=cmd_import)

    sh = sub.add_parser("sheet", help="contact sheet of all pictures (contact_sheet.jpg)")
    sh.add_argument("project")
    sh.set_defaults(func=cmd_sheet)

    bd = sub.add_parser("build", help="build the video")
    bd.add_argument("project")
    bd.add_argument("--preview", action="store_true", help="half resolution, faster")
    bd.add_argument("--res", choices=["720p", "1080p", "2k", "4k"], help="export size (2k = 2560x1440)")
    bd.add_argument("--captions", choices=["white_outline", "yellow_pop", "scene"],
                    help="burn captions in: white_outline | yellow_pop | scene (per-scene style)")
    bd.add_argument("--allow-missing", action="store_true", help="use placeholders for missing pictures")
    bd.add_argument("--offline", action="store_true", help="stand-in voice and placeholders (testing only)")
    bd.set_defaults(func=cmd_build)

    ch = sub.add_parser("chapters", help="YouTube chapter lines from the final timings (chapters.txt)")
    ch.add_argument("project")
    ch.set_defaults(func=cmd_chapters)

    sl = sub.add_parser("sfx-list", help="list available sound names")
    sl.set_defaults(func=cmd_sfx_list)

    vp = sub.add_parser("voices", help="make a short audio sample of 50 voices in voices/ (index.html to listen)")
    vp.set_defaults(func=cmd_voices)
    sfp = sub.add_parser("sfx-fetch", help="download the free SFXMint sound pack (CC0) into sfx_library/_sfxmint")
    sfp.set_defaults(func=cmd_sfx_fetch)

    dr = sub.add_parser("doctor", help="check tools and models")
    dr.set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args.func(args)


if __name__ == "__main__":
    main()
