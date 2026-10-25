"""Image generation with a content-addressed cache and style-safe fallbacks.

Providers:
  hf_flux     - Hugging Face Space (default black-forest-labs/FLUX.1-schnell) via gradio_client
  placeholder - offline procedural drawing in the right style (used for tests and as fallback)

Cache file names are a hash of provider + model + prompt + seed + size, so changing a
scene's style or prompt never reuses a stale picture.
"""

from __future__ import annotations

import math
import os
import random
import shutil
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .util import log, read_json, stable_hash, write_json

_CLIENTS: dict = {}


def _font(size: int):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------- providers

def _hf_flux(req: dict, token: Optional[str], out_path: str) -> None:
    from gradio_client import Client  # imported lazily: optional dependency
    model = req.get("model") or "black-forest-labs/FLUX.1-schnell"
    client = _CLIENTS.get(model)
    if client is None:
        try:
            client = Client(model, token=token) if token else Client(model)
        except TypeError:  # older gradio_client
            client = Client(model, hf_token=token) if token else Client(model)
        _CLIENTS[model] = client
    res = client.predict(
        prompt=req["prompt"], seed=int(req["seed"]), randomize_seed=False,
        width=int(req["width"]), height=int(req["height"]),
        num_inference_steps=int(req.get("steps", 4)), api_name="/infer",
    )
    tmp = res[0] if isinstance(res, (list, tuple)) else res
    if isinstance(tmp, dict):
        tmp = tmp.get("path") or tmp.get("url")
    Image.open(tmp).convert("RGB").save(out_path, "PNG")


def _stick_figure(d: ImageDraw.ImageDraw, x: float, y: float, h: float, color, width: int, rng, crown=False):
    head = h * 0.13
    neck = y - h + head * 2
    d.ellipse([x - head, y - h, x + head, y - h + head * 2], outline=color, width=width)
    hip = y - h * 0.42
    d.line([x, neck, x, hip], fill=color, width=width)
    arm_y = neck + h * 0.1
    a1, a2 = rng.uniform(-0.6, 0.3), rng.uniform(-0.3, 0.6)
    d.line([x, arm_y, x - h * 0.28, arm_y + h * (0.22 + a1 * 0.3)], fill=color, width=width)
    d.line([x, arm_y, x + h * 0.28, arm_y + h * (0.22 + a2 * 0.3)], fill=color, width=width)
    d.line([x, hip, x - h * 0.2, y], fill=color, width=width)
    d.line([x, hip, x + h * 0.2, y], fill=color, width=width)
    if crown:
        cy = y - h - head * 0.2
        pts = [(x - head, cy), (x - head, cy - head), (x - head * 0.5, cy - head * 0.5), (x, cy - head * 1.2),
               (x + head * 0.5, cy - head * 0.5), (x + head, cy - head), (x + head, cy)]
        d.polygon(pts, fill=(222, 180, 40), outline=color)


def _crown(d, cx, cy, w, outline, fill=(214, 168, 40)):
    h = w * 0.7
    pts = [(cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 4), (cx - w / 4, cy + h / 8), (cx, cy - h / 2),
           (cx + w / 4, cy + h / 8), (cx + w / 2, cy - h / 4), (cx + w / 2, cy + h / 2)]
    d.polygon(pts, fill=fill, outline=outline)
    d.line(pts + [pts[0]], fill=outline, width=max(3, int(w * 0.04)))
    for k in (-0.25, 0, 0.25):
        r = w * 0.05
        d.ellipse([cx + k * w - r, cy + h * 0.28 - r, cx + k * w + r, cy + h * 0.28 + r], fill=(170, 20, 30))


def _placeholder(req: dict, out_path: str) -> None:
    """Draw a recognisable stand-in in the requested style (no network)."""
    w, h = int(req["width"]), int(req["height"])
    rng = random.Random(stable_hash(req["prompt"], req["seed"]))
    style, kind = req.get("style", "oil"), req.get("kind", "scene")
    subject = (req.get("subject") or req["prompt"]).lower()

    if style == "stickman":
        bg = (255, 255, 255) if kind != "scene" else (247, 243, 234)
        img = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(img)
        ink = (20, 20, 20)
        lw = max(4, h // 90)
        if kind == "prop":
            _crown(d, w / 2, h / 2, min(w, h) * 0.55, ink) if "crown" in subject else \
                d.ellipse([w * 0.3, h * 0.25, w * 0.7, h * 0.75], outline=ink, width=lw, fill=(200, 60, 50))
        elif kind == "character":
            _stick_figure(d, w / 2, h * 0.92, h * 0.82, ink, lw, rng, crown="king" in subject and "crown" in subject)
        else:
            d.line([0, h * 0.82, w, h * 0.82], fill=(60, 60, 60), width=max(2, lw // 2))
            n = rng.randint(1, 3)
            for i in range(n):
                x = w * (0.25 + 0.5 * (i + 0.5) / n) + rng.uniform(-30, 30)
                _stick_figure(d, x, h * 0.82, h * rng.uniform(0.38, 0.5), ink, lw, rng)
            if rng.random() < 0.6:  # a simple prop: a column / boat / sun
                px = w * rng.choice([0.12, 0.85])
                d.rectangle([px - w * 0.03, h * 0.35, px + w * 0.03, h * 0.82], outline=ink, width=lw)
                d.rectangle([px - w * 0.05, h * 0.32, px + w * 0.05, h * 0.36], outline=ink, width=lw)
            d.ellipse([w * 0.82, h * 0.08, w * 0.92, h * 0.08 + w * 0.1], outline=(220, 140, 30), width=lw)
    else:  # oil-like
        palette = [(14, 47, 68), (197, 160, 89), (139, 0, 0), (250, 240, 230), (120, 72, 40), (40, 30, 24)]
        if kind != "scene":
            img = Image.new("RGB", (w, h), (205, 205, 205))
            d = ImageDraw.Draw(img)
            if kind == "prop":
                if "crown" in subject:
                    _crown(d, w / 2, h / 2, min(w, h) * 0.55, (90, 60, 10))
                else:
                    d.ellipse([w * 0.3, h * 0.25, w * 0.7, h * 0.75], fill=(150, 110, 50))
            else:  # painted figure silhouette with cloak
                cx, top, bot = w / 2, h * 0.06, h * 0.97
                hh = bot - top
                d.ellipse([cx - hh * 0.07, top, cx + hh * 0.07, top + hh * 0.15], fill=(196, 150, 112))
                d.polygon([(cx - hh * 0.16, top + hh * 0.17), (cx + hh * 0.16, top + hh * 0.17),
                           (cx + hh * 0.24, bot), (cx - hh * 0.24, bot)], fill=(139, 20, 20))
                d.rectangle([cx - hh * 0.1, top + hh * 0.17, cx + hh * 0.1, top + hh * 0.55], fill=(184, 140, 70))
                if "crown" in subject:
                    _crown(d, cx, top - hh * 0.01, hh * 0.16, (90, 60, 10))
            img = img.filter(ImageFilter.GaussianBlur(1.2))
        else:
            top, bottom = rng.sample(palette[:4], 2)
            img = Image.new("RGB", (w, h))
            px = img.load()
            for y in range(h):
                t = y / max(1, h - 1)
                c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
                for x in range(w):
                    px[x, y] = c
            d = ImageDraw.Draw(img, "RGBA")
            hor = h * rng.uniform(0.55, 0.72)
            d.polygon([(0, h), (0, hor), (w * 0.3, hor - h * 0.12), (w * 0.55, hor - h * 0.02),
                       (w * 0.8, hor - h * 0.16), (w, hor - h * 0.05), (w, h)], fill=(40, 30, 24, 230))
            for _ in range(500):  # brush dabs
                c = rng.choice(palette) + (rng.randint(30, 90),)
                x, y = rng.uniform(0, w), rng.uniform(0, h)
                r = rng.uniform(4, 26)
                d.ellipse([x - r * 1.8, y - r * 0.6, x + r * 1.8, y + r * 0.6], fill=c)
            sx = w * rng.uniform(0.2, 0.8)
            d.ellipse([sx - h * 0.09, h * 0.12, sx + h * 0.09, h * 0.3], fill=(250, 220, 150, 200))
            img = img.filter(ImageFilter.GaussianBlur(1.5))
    if kind != "scene":   # layers get no label (it would end up in the cut-out)
        img.save(out_path, "PNG")
        return
    # small debug label so placeholders are identifiable
    d = ImageDraw.Draw(img)
    label = "PLACEHOLDER " + (req.get("subject") or "")[:70]
    f = _font(max(12, h // 40))
    d.rectangle([0, h - h // 22 - 6, w, h], fill=(0, 0, 0) if style == "oil" else (230, 226, 216))
    d.text((8, h - h // 22 - 3), label, fill=(255, 255, 255) if style == "oil" else (60, 60, 60), font=f)
    img.save(out_path, "PNG")


# --------------------------------------------------------------------------- API

class ImageGenerator:
    def __init__(self, cache_dir: str, hf_token: Optional[str] = None, force_provider: Optional[str] = None):
        self.cache_dir = Path(cache_dir) / "images"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hf_token = hf_token
        self.force_provider = force_provider
        self.report: list[dict] = []
        self._hf_dead = False

    def generate(self, req: dict) -> dict:
        """req: style, kind, prompt, subject, seed, width, height, provider, model, steps."""
        req = dict(req)
        if self.force_provider:
            req["provider"] = self.force_provider
        provider = req.get("provider", "hf_flux")
        key = stable_hash(provider, req.get("model"), req["prompt"], req["seed"], req["width"], req["height"],
                          req.get("steps"), req.get("kind"))
        out = self.cache_dir / f"{req.get('style', 'x')}_{key}.png"
        meta_path = Path(str(out) + ".json")
        if out.exists() and meta_path.exists():
            meta = read_json(meta_path)
            self.report.append(meta | {"cached": True})
            return meta

        used, fallback, error = provider, False, None
        if provider == "hf_flux" and not self._hf_dead:
            for attempt in range(3):
                try:
                    r = dict(req, seed=int(req["seed"]) + attempt * 9973)
                    _hf_flux(r, self.hf_token, str(out))
                    error = None
                    break
                except Exception as e:  # network, quota, space asleep...
                    error = f"{type(e).__name__}: {e}"
                    log(f"    image attempt {attempt + 1} failed: {error[:160]}")
                    if "Could not fetch config" in str(e) or "Name or service not known" in str(e) \
                            or "ConnectError" in error:
                        self._hf_dead = True  # offline: don't wait on every image
                        break
                    time.sleep(4 * (attempt + 1))
            if error:
                fallback, used = True, "placeholder"
        elif provider == "hf_flux":
            fallback, used, error = True, "placeholder", "Hugging Face unreachable earlier in this run"
        elif provider not in ("placeholder",):
            raise ValueError(f"Unknown image provider '{provider}' (hf_flux, placeholder)")

        if used == "placeholder":
            _placeholder(req, str(out))
        meta = {"path": str(out), "provider": used, "fallback": fallback, "error": error,
                "style": req.get("style"), "kind": req.get("kind"), "prompt": req["prompt"], "seed": req["seed"]}
        write_json(meta_path, meta)
        self.report.append(meta | {"cached": False})
        return meta

    def from_file(self, path: str, style: str, kind: str = "scene") -> dict:
        key = stable_hash(os.path.abspath(path), os.path.getmtime(path))
        out = self.cache_dir / f"file_{key}{Path(path).suffix.lower() or '.png'}"
        if not out.exists():
            shutil.copyfile(path, out)
        return {"path": str(out), "provider": "file", "fallback": False, "style": style, "kind": kind,
                "prompt": None, "seed": None}
