"""Per-style image clean-up and character cut-outs."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .util import log, stable_hash


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _cover(img: Image.Image, w: int, h: int, focus=(0.5, 0.5)) -> Image.Image:
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(round(sw * scale)), int(round(sh * scale))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x = int((nw - w) * focus[0])
    y = int((nh - h) * focus[1])
    return img.crop((x, y, x + w, y + h))


def _realesrgan(src: str, dst: str, exe: str) -> bool:
    try:
        subprocess.run([exe, "-i", src, "-o", dst, "-s", "4"], check=True, capture_output=True, timeout=600)
        return os.path.exists(dst)
    except Exception as e:  # missing GPU / binary
        log(f"    Real-ESRGAN skipped ({e}); using Lanczos")
        return False


class PostProcessor:
    def __init__(self, cache_dir: str, canvas: dict, realesrgan_path: Optional[str] = None):
        self.dir = Path(cache_dir) / "processed"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cw, self.ch = int(canvas["width"]), int(canvas["height"])
        # work at 4/3 of the canvas so pans/zooms/crops stay sharp
        self.ww, self.wh = int(self.cw * 4 / 3) // 2 * 2, int(self.ch * 4 / 3) // 2 * 2
        self.realesrgan = realesrgan_path

    # ------------------------------------------------------------------ backgrounds
    def scene_image(self, src: str, style_name: str, style: dict) -> str:
        post = style.get("post", {})
        key = stable_hash("scene", src, os.path.getmtime(src), style_name, post, self.ww, self.wh)
        out = self.dir / f"{style_name}_{key}.png"
        if out.exists():
            return str(out)
        source = src
        if post.get("upscale") == "realesrgan" and self.realesrgan:
            tmp = str(self.dir / f"esr_{key}.png")
            if _realesrgan(src, tmp, self.realesrgan):
                source = tmp
        img = Image.open(source).convert("RGB")
        img = _cover(img, self.ww, self.wh)
        if "paper" in post:
            img = self._paper(img, post)
        else:
            img = self._grade(img, post)
        if post.get("sharpen"):
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=int(80 * post["sharpen"]), threshold=2))
        img.save(out, "PNG")
        return str(out)

    def _grade(self, img: Image.Image, post: dict) -> Image.Image:
        if post.get("contrast"):
            img = ImageEnhance.Contrast(img).enhance(post["contrast"])
        if post.get("saturation"):
            img = ImageEnhance.Color(img).enhance(post["saturation"])
        a = np.asarray(img).astype(np.float32) / 255.0
        warm = float(post.get("warmth", 0))
        if warm:
            a[..., 0] = np.clip(a[..., 0] + warm, 0, 1)
            a[..., 2] = np.clip(a[..., 2] - warm, 0, 1)
        if post.get("tint") and post.get("tint_strength"):
            tint = np.array(_hex(post["tint"]), dtype=np.float32) / 255.0
            s = float(post["tint_strength"])
            lum = a.mean(axis=2, keepdims=True)
            a = a * (1 - s) + (lum * tint * 1.6) * s   # tint the mids, keep shadows/highlights
        return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))

    def _paper(self, img: Image.Image, post: dict) -> Image.Image:
        paper = np.array(_hex(post.get("paper", "#F7F3EA")), dtype=np.float32) / 255.0
        thr = float(post.get("paper_threshold", 0.82))
        a = np.asarray(img).astype(np.float32) / 255.0
        lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        sat = a.max(axis=2) - a.min(axis=2)
        # light, unsaturated pixels become exactly the paper colour; lines/accents are kept
        m = np.clip((lum - thr) / (1 - thr + 1e-6), 0, 1) * np.clip(1 - sat * 3, 0, 1)
        m = m[..., None]
        a = a * (1 - m) + paper * m
        # darken line work a touch for crispness
        dark = np.clip((0.45 - lum) / 0.45, 0, 1)[..., None]
        a = a * (1 - 0.35 * dark)
        tex = float(post.get("paper_texture", 0))
        if tex:
            rng = np.random.default_rng(7)
            noise = rng.normal(0, tex, a.shape[:2]).astype(np.float32)
            noise = np.asarray(Image.fromarray(((noise + 0.5) * 255).clip(0, 255).astype(np.uint8))
                               .filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32) / 255.0 - 0.5
            a = a + noise[..., None] * m
        return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))

    # ------------------------------------------------------------------ cut-outs
    def cutout(self, src: str, method: str = "auto") -> str:
        key = stable_hash("cut", src, os.path.getmtime(src), method)
        out = self.dir / f"cutout_{key}.png"
        if out.exists():
            return str(out)
        img = Image.open(src).convert("RGB")
        rgba = None
        if method in ("auto", "rembg"):
            rgba = self._rembg(img)
            if rgba is None and method == "rembg":
                log("    rembg not installed (pip install rembg); using colour keying")
        if rgba is None:
            rgba = self._threshold(img) if method == "threshold" else self._key(img)
        bbox = rgba.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
        if bbox:
            pad = 6
            bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                    min(rgba.width, bbox[2] + pad), min(rgba.height, bbox[3] + pad))
            rgba = rgba.crop(bbox)
        rgba.save(out, "PNG")
        return str(out)

    @staticmethod
    def _rembg(img: Image.Image) -> Optional[Image.Image]:
        try:
            from rembg import remove  # optional dependency
        except Exception:
            return None
        try:
            return remove(img).convert("RGBA")
        except Exception as e:
            log(f"    rembg failed ({e}); using colour keying")
            return None

    @staticmethod
    def _threshold(img: Image.Image) -> Image.Image:
        """For drawings on white/paper: dark lines and colours stay, paper goes transparent.
        Enclosed light areas (inside a head) are kept by flood-filling from the border only."""
        a = np.asarray(img).astype(np.float32) / 255.0
        lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        sat = a.max(axis=2) - a.min(axis=2)
        bgness = np.clip((lum - 0.72) / 0.2, 0, 1) * np.clip(1 - sat * 4, 0, 1)
        alpha = 1 - bgness
        # only background connected to the border is removed
        mask = Image.fromarray(((bgness > 0.5) * 255).astype(np.uint8))
        from PIL import ImageDraw
        filled = mask.copy()
        w, h = filled.size
        for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1),
                     (0, h // 2), (w - 1, h // 2)]:
            if filled.getpixel(seed) == 255:
                ImageDraw.floodfill(filled, seed, 128)
        enclosed = (np.asarray(filled) == 255)   # paper-coloured but not reachable from the border
        alpha = np.where(enclosed, 1.0, alpha)
        rgba = np.dstack([a, alpha]).clip(0, 1)
        return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")

    @staticmethod
    def _key(img: Image.Image) -> Image.Image:
        """Generic chroma-style key: background colour estimated from the image border."""
        a = np.asarray(img).astype(np.float32) / 255.0
        border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        bg = np.median(border, axis=0)
        dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
        # robust to a few border pixels that are not background (feet touching the edge, labels)
        spread = min(0.12, float(np.percentile(np.sqrt(((border - bg) ** 2).sum(axis=1)), 60)))
        lo, hi = spread + 0.04, spread + 0.16
        alpha = np.clip((dist - lo) / (hi - lo), 0, 1)
        # only background CONNECTED to the border is removed, so a white head / white hands / a white
        # toga outlined in black stay solid (flood fill from a 1-px padded frame)
        from PIL import ImageDraw
        h, w = alpha.shape
        m = np.zeros((h + 2, w + 2), np.uint8)
        m[1:-1, 1:-1] = np.where(alpha < 0.98, 255, 0)
        m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = 255
        mi = Image.fromarray(m).copy()   # copy: fromarray may share a read-only buffer
        ImageDraw.floodfill(mi, (0, 0), 128)
        reach = np.asarray(mi)[1:-1, 1:-1] == 128
        alpha = np.where(reach, alpha, 1.0)
        alpha_img = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)) \
            .filter(ImageFilter.GaussianBlur(0.8))
        # remove background colour spill on soft edges
        al = np.asarray(alpha_img).astype(np.float32)[..., None] / 255.0
        rgb = np.where(al > 0.02, (a - bg * (1 - al)) / np.maximum(al, 0.02), a).clip(0, 1)
        rgba = np.dstack([rgb, al[..., 0]])
        return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
