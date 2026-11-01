r"""Where a project keeps its files, and small tools to keep that tidy.

<main folder>\projects\<slug>\
    script.md  project.json  image_jobs.json  image_prompts.md  contact_sheet.jpg
    build.bat  mp4.bat  preview.bat  status.bat  files.bat  open_output.bat   (+ .sh)   launchers for THIS project
    images\            every picture as .jpg: s05c_1.jpg, s12a_bg.jpg, cast_<name>.jpg, cast_<name>_walk1.jpg
    images_unused\     pictures that match no job, or were replaced (nothing is ever deleted)
    output\            <slug>.mp4, <slug>.srt, <slug>_mix.m4a, chapters.txt, package.md, capcut_draft\
    output\work\       voice\ (one wav + .json word timings per scene), music_*.wav, stems\ (voice/sfx/amb/music), plan.json
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from .util import log, read_json

IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


# --------------------------------------------------------------------------- launchers

def write_launchers(pdir: Path, repo_root: Path) -> list[str]:
    """Small .bat / .sh files INSIDE the project folder that run the engine for this project only."""
    pdir = Path(pdir)
    name = pdir.name
    engine_bat = Path(repo_root) / "vdo.bat"
    engine_sh = Path(repo_root) / "vdo.sh"
    # (file, engine command and options, what it does)
    items = [
        ("build", "build", "Build and push this project to CapCut as an editable draft (close CapCut first; e.g. --res 2k --captions yellow_pop)"),
        ("mp4", "build --mp4-only", "Render the MP4 on this PC instead (no CapCut)"),
        ("preview", "build --preview", "Quick half-size build pushed to CapCut"),
        ("status", "status", "List the pictures still missing"),
        ("files", "files", "List everything saved for this project, with counts"),
    ]
    written = []
    for fn, cmd, why in items:
        bat = (f"@echo off\r\nrem {name}: {why}\r\n"
               f"\"{engine_bat}\" {cmd} \"%~dp0project.json\" %*\r\n"
               f"echo %cmdcmdline% | find /i \"/c\" >nul && pause\r\n")
        (pdir / f"{fn}.bat").write_bytes(bat.encode("utf-8"))
        sh = (f"#!/usr/bin/env bash\n# {name}: {why}\n"
              f"\"{engine_sh}\" {cmd} \"$(cd \"$(dirname \"${{BASH_SOURCE[0]}}\")\" && pwd)/project.json\" \"$@\"\n")
        (pdir / f"{fn}.sh").write_text(sh, encoding="utf-8", newline="\n")
        try:
            os.chmod(pdir / f"{fn}.sh", 0o755)
        except OSError:
            pass
        written += [f"{fn}.bat", f"{fn}.sh"]
    (pdir / "open_output.bat").write_bytes(b"@echo off\r\nif not exist \"%~dp0output\" mkdir \"%~dp0output\"\r\nstart \"\" \"%~dp0output\"\r\n")
    written.append("open_output.bat")
    return written


# --------------------------------------------------------------------------- pictures

def park(path: Path, unused_dir: Path) -> Path:
    """Move a file into images_unused (never delete); a clash gets a timestamp."""
    unused_dir.mkdir(parents=True, exist_ok=True)
    dst = unused_dir / path.name
    if dst.exists():
        dst = unused_dir / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}"
    shutil.move(str(path), dst)
    return dst


def tidy_images(pdir: Path) -> list[str]:
    """Pictures in images\\ that match no job in image_jobs.json go to images_unused\\."""
    pdir = Path(pdir)
    jp = pdir / "image_jobs.json"
    images = pdir / "images"
    if not jp.exists() or not images.exists():
        return []
    wanted = {Path(j["file"]).stem for j in read_json(jp)}
    moved = []
    for f in sorted(images.iterdir()):
        if f.is_file() and f.suffix.lower() in IMG_EXTS and f.stem not in wanted:
            park(f, pdir / "images_unused")
            moved.append(f.name)
    return moved


def to_jpg(src: Path, dst: Path, quality: int = 95) -> None:
    """Save any picture as a high-quality .jpg (no chroma subsampling, so green-screen edges stay clean)."""
    from PIL import Image
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    im.save(dst, "JPEG", quality=quality, subsampling=0, optimize=True)


# --------------------------------------------------------------------------- report

def _count(d: Path, pattern: str) -> int:
    return len(list(d.glob(pattern))) if d.exists() else 0


def report(pdir: Path) -> dict:
    """Everything saved for a project, with counts. Returns the numbers; log() shows them."""
    pdir = Path(pdir)
    out = pdir / "output"
    work = out / "work"
    r: dict = {"project_folder": str(pdir)}
    jobs = read_json(pdir / "image_jobs.json") if (pdir / "image_jobs.json").exists() else []
    names = {Path(j["file"]).stem: j for j in jobs}
    have = {f.stem for f in (pdir / "images").glob("*") if f.suffix.lower() in IMG_EXTS} if (pdir / "images").exists() else set()
    kinds: dict[str, list[int]] = {}
    for stem, j in names.items():
        k = j.get("kind", "scene")
        k = {"cast": "cast masters", "cast_pose": "cast poses", "scene": "scene pictures",
             "background": "backgrounds", "prop": "props"}.get(k, k)
        kinds.setdefault(k, [0, 0])
        kinds[k][1] += 1
        kinds[k][0] += stem in have
    r["pictures"] = kinds
    r["images_unused"] = sum(1 for f in (pdir / "images_unused").glob("*")) if (pdir / "images_unused").exists() else 0
    r["voice_files"] = _count(work / "voice", "*.wav") + _count(work / "voice", "*.mp3")
    r["voice_timings"] = _count(work / "voice", "*.json")
    r["music_files"] = _count(work, "music_*.wav")
    r["stems"] = sorted(p.name for p in (work / "stems").glob("*.wav")) if (work / "stems").exists() else []
    r["outputs"] = sorted(p.name for p in out.glob("*") if p.is_file()) if out.exists() else []
    r["capcut_draft"] = (out / "capcut_draft").exists()
    return r


def show_report(pdir: Path) -> None:
    r = report(pdir)
    log(f"Project folder: {r['project_folder']}")
    log(f"Pictures (images\\, .jpg):")
    for k, (done, total) in r["pictures"].items():
        log(f"  {k:<15} {done}/{total}")
    total_have = sum(v[0] for v in r["pictures"].values())
    total_all = sum(v[1] for v in r["pictures"].values())
    log(f"  {'total':<15} {total_have}/{total_all}")
    log(f"  images_unused\\  {r['images_unused']} file(s)")
    log(f"Narration (output\\work\\voice\\): {r['voice_files']} audio file(s), {r['voice_timings']} word-timing file(s)")
    log(f"Music (output\\work\\): {r['music_files']} file(s); stems (output\\work\\stems\\): {', '.join(r['stems']) or '-'}")
    log(f"Output (output\\): {len(r['outputs'])} file(s): {', '.join(r['outputs']) or '-'}")
    if r["capcut_draft"]:
        log("CapCut draft: output\\capcut_draft\\")


# --------------------------------------------------------------------------- main folder

def init_main(main: str, config_path: Path) -> Path:
    """Create <main>\\projects and remember the main folder in config.json."""
    main_p = Path(main).expanduser()
    (main_p / "projects").mkdir(parents=True, exist_ok=True)
    data = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["main_folder"] = str(main_p)
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return main_p
