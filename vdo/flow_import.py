"""Bring Google Flow pictures into a project.

  downloads : files the helper saved as vdo__<project>__<job id>.<ext> (moved from ~/Downloads)
  chunks    : text files holding the helper's vdo.chunk(i) output (remote sessions)
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
from pathlib import Path

from .util import log

EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _clear_old(images: Path, job_id: str):
    for ext in EXTS:
        p = images / f"{job_id}{ext}"
        if p.exists():
            p.unlink()


def from_downloads(project_dir: Path, project_name: str, folder: str | None = None) -> list[str]:
    src = Path(folder or Path.home() / "Downloads")
    images = project_dir / "images"
    images.mkdir(exist_ok=True)
    pat = re.compile(rf"^vdo__{re.escape(project_name)}__(.+?)(?: \(\d+\))?(\.\w+)$")
    found = {}
    for f in sorted(src.iterdir(), key=lambda p: p.stat().st_mtime):   # newest wins
        m = pat.match(f.name)
        if m and m.group(2).lower() in EXTS:
            found[m.group(1)] = f
    moved = []
    for job_id, f in found.items():
        _clear_old(images, job_id)
        dst = images / f"{job_id}{f.suffix.lower()}"
        shutil.move(str(f), dst)
        moved.append(job_id)
    for f in src.iterdir():   # leftovers from earlier tries
        if pat.match(f.name):
            f.unlink()
    return moved


def _text_of(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # a tool-result file may be JSON ([{"type":"text","text":"..."}]) wrapping a JSON string
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            raw = "".join(x.get("text", "") for x in data if isinstance(x, dict))
        elif isinstance(data, str):
            raw = data
    except Exception:
        pass
    raw = raw.split("\n\n(captured at origin")[0].strip()
    if raw.startswith('"'):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = raw.strip('"')
    return raw


def from_chunks(project_dir: Path, files: list[str]) -> list[str]:
    parts = {}
    for f in files:
        t = _text_of(Path(f))
        m = re.search(r"(?:VDO)?CHUNK(\d+)\|", t)
        if m:
            parts[int(m.group(1))] = t[m.end():]
    if not parts:
        raise RuntimeError("No VDOCHUNK data found in those files.")
    n = max(parts) + 1
    gaps = [i for i in range(n) if i not in parts]
    if gaps:
        raise RuntimeError(f"Missing chunk(s): {gaps}")
    images = project_dir / "images"
    images.mkdir(exist_ok=True)
    saved = []
    for line in "".join(parts[i] for i in range(n)).split("\n"):
        if ":" not in line:
            continue
        job_id, data = line.split(":", 1)
        blob = base64.b64decode(data)
        ext = ".png" if blob[:4] == b"\x89PNG" else ".webp" if blob[8:12] == b"WEBP" else ".jpg"
        _clear_old(images, job_id)
        (images / f"{job_id}{ext}").write_bytes(blob)
        saved.append(job_id)
    return saved


def contact_sheet(project_dir: Path, out: Path | None = None) -> str:
    """One picture showing every image in the project, labelled - for a quick visual check."""
    from PIL import Image, ImageDraw
    files = sorted(p for p in (project_dir / "images").iterdir() if p.suffix.lower() in EXTS)
    if not files:
        raise RuntimeError("No pictures in images/ yet.")
    W, H, cols = 480, 270, 4
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W, rows * (H + 28)), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        im.thumbnail((W, H))
        x, y = (i % cols) * W, (i // cols) * (H + 28)
        sheet.paste(im, (x + (W - im.width) // 2, y + 28 + (H - im.height) // 2))
        d.text((x + 8, y + 7), f.stem, fill=(255, 255, 255))
    out = out or project_dir / "contact_sheet.jpg"
    sheet.save(out, quality=88)
    return str(out)
