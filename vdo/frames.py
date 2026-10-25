"""Frame renderer: pans/zooms on pictures, overlay scenes with cut-out layers,
eased keyframes, motion blur (sub-frame shutter), camera shake, flashes, grain, vignette.

Every cut becomes a short silent MP4 (frames piped straight into ffmpeg). Transitions
between cuts are added later by the ffmpeg backend.
"""

from __future__ import annotations

import math
import random
import subprocess
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .util import ease, lerp, stable_hash

# ----------------------------------------------------------------------------- helpers


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def screen_fx_filter(frame_fx: Optional[dict]) -> Optional[str]:
    """Grain and vignette fixed to the screen, done by ffmpeg while encoding (fast, in C)."""
    if not frame_fx:
        return None
    parts = []
    vig = float(frame_fx.get("vignette", 0) or 0)
    grain = float(frame_fx.get("grain", 0) or 0)
    if vig > 0:
        parts.append(f"vignette=angle={min(1.4, 0.25 + vig * 1.6):.3f}:eval=init")
    if grain > 0:
        parts.append(f"noise=alls={max(1, int(grain * 200))}:allf=t+u")
    return ",".join(parts) or None


class Encoder:
    def __init__(self, ffmpeg: str, out_path: str, w: int, h: int, fps: int, crf: int = 18,
                 preset: str = "medium", vf: Optional[str] = None):
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-r", str(fps), "-movflags", "+faststart", out_path]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, arr):
        if isinstance(arr, Image.Image):
            self.proc.stdin.write(arr.tobytes())
        else:
            self.proc.stdin.write(np.ascontiguousarray(arr, dtype=np.uint8).tobytes())

    def close(self):
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg encode failed: {err[-1500:]}")


# ----------------------------------------------------------------------------- camera moves

VARIANT_ZOOM = [1.0, 1.32, 1.65, 1.32, 1.5]


def _focus_for(key: str, variant: int):
    if variant == 0:
        return 0.5, 0.5
    rng = random.Random(stable_hash(key, variant))
    return rng.choice([0.33, 0.5, 0.67]), rng.choice([0.4, 0.5, 0.6])


def camera(preset: str, p: float, base_zoom: float, focus, amount: float, easing: str, clip_len: float):
    """Return (zoom, cx, cy) in normalised source coords for progress p in [0,1].
    zoom > 1 means tighter framing."""
    fx, fy = focus
    e = ease(easing, p)
    if preset in (None, "none", "static"):
        return base_zoom, fx, fy
    if preset == "push_in":
        return base_zoom * (1 + amount * e), fx, fy
    if preset == "pull_out":
        return base_zoom * (1 + amount * (1 - e)), fx, fy
    if preset in ("pan_left", "pan_right"):
        z = base_zoom * (1 + amount * 0.7)
        span = (1 - 1 / z) * 0.5
        d = -1 if preset == "pan_left" else 1
        return z, fx + d * span * (e - 0.5) * 1.6, fy
    if preset in ("pan_up", "pan_down"):
        z = base_zoom * (1 + amount * 0.7)
        span = (1 - 1 / z) * 0.5
        d = -1 if preset == "pan_up" else 1
        return z, fx, fy + d * span * (e - 0.5) * 1.6
    if preset == "pop_in":
        # quick springy settle in the first ~0.4 s, then a slow drift
        t = p * clip_len
        settle = ease("easeOutBack", min(1.0, t / 0.4))
        z = base_zoom * (0.94 + 0.06 * settle) * (1 + amount * 0.5 * p)
        return z, fx, fy
    if preset in ("nudge_left", "nudge_right"):
        t = p * clip_len
        k = ease("easeOutBack", min(1.0, t / 0.5))
        d = -1 if preset == "nudge_left" else 1
        z = base_zoom * (1 + amount)
        span = (1 - 1 / z) * 0.5
        return z, fx + d * span * (0.6 * k + 0.25 * p), fy
    raise ValueError(f"Unknown motion preset '{preset}'")


def view_transform(src: Image.Image, out_w: int, out_h: int, zoom: float, cx: float, cy: float,
                   fill=(0, 0, 0), dx_px: float = 0, dy_px: float = 0, resample=Image.Resampling.BILINEAR):
    """Render the source as seen by a camera: zoom 1 shows the whole source (cover).
    Uses Pillow's sub-pixel box resize (smooth motion, antialiased)."""
    sw, sh = src.size
    vw = sw / zoom
    vh = vw * out_h / out_w
    if vh > sh / zoom:
        vh = sh / zoom
        vw = vh * out_w / out_h
    x0 = cx * sw - vw / 2
    y0 = cy * sh - vh / 2
    if zoom >= 1:
        x0 = min(max(0.0, x0), sw - vw)
        y0 = min(max(0.0, y0), sh - vh)
    sx, sy = out_w / vw, out_h / vh          # output px per source px
    x0 -= dx_px / sx
    y0 -= dy_px / sy
    x1, y1 = x0 + vw, y0 + vh
    if x0 >= 0 and y0 >= 0 and x1 <= sw and y1 <= sh:
        return src.resize((out_w, out_h), resample, box=(x0, y0, x1, y1))
    # part of the view is outside the picture (zoomed out / shaken): draw the inside, pad with fill
    bx0, by0, bx1, by1 = max(0.0, x0), max(0.0, y0), min(float(sw), x1), min(float(sh), y1)
    canvas = Image.new("RGB", (out_w, out_h), fill)
    if bx1 - bx0 < 1 or by1 - by0 < 1:
        return canvas
    ox, oy = (bx0 - x0) * sx, (by0 - y0) * sy
    tw, th = max(1, int(round((bx1 - bx0) * sx))), max(1, int(round((by1 - by0) * sy)))
    part = src.resize((tw, th), resample, box=(bx0, by0, bx1, by1))
    canvas.paste(part, (int(round(ox)), int(round(oy))))
    return canvas


# ----------------------------------------------------------------------------- overlays

def _paste(frame: Image.Image, im: Image.Image, left: float, top: float) -> None:
    """alpha_composite that tolerates layers partly (or fully) off-screen."""
    x, y = int(round(left)), int(round(top))
    W, H = frame.size
    if x >= W or y >= H or x + im.width <= 0 or y + im.height <= 0:
        return
    cx0, cy0 = max(0, -x), max(0, -y)
    cx1, cy1 = min(im.width, W - x), min(im.height, H - y)
    if cx0 or cy0 or cx1 < im.width or cy1 < im.height:
        im = im.crop((cx0, cy0, cx1, cy1))
    frame.alpha_composite(im, (x + cx0, y + cy0))


class Layer:
    def __init__(self, spec: dict, images: dict[str, Image.Image], canvas_h: int):
        self.spec = spec
        self.id = spec["id"]
        self.kind = spec.get("kind", "character")
        self.base_h = float(spec.get("height", 0.6)) * canvas_h
        self.images = images             # {"base": img, "pose_0": img, ...}
        self.kfs = spec["keyframes"]
        self.follow = spec.get("follow", [])
        self.anchor = spec.get("anchor", "bottom" if self.kind == "character" else "center")
        self._cache: dict = {}

    def image_at(self, t: float) -> Image.Image:
        img = self.images["base"]
        for i, pose in enumerate(self.spec.get("poses", [])):
            if t >= pose["t"]:
                img = self.images[f"pose_{i}"]
        return img

    def props_at(self, t: float) -> dict:
        kfs = self.kfs
        keys = ("x", "y", "scale", "rot", "opacity")
        defaults = {"x": 0.5, "y": 0.9, "scale": 1.0, "rot": 0.0, "opacity": 1.0}
        if t <= kfs[0]["t"]:
            k = kfs[0]
            return {n: float(k.get(n, defaults[n])) for n in keys}
        if t >= kfs[-1]["t"]:
            last = {n: defaults[n] for n in keys}
            for k in kfs:  # carry forward every specified value
                for n in keys:
                    if n in k:
                        last[n] = float(k[n])
            return last
        state = {n: defaults[n] for n in keys}
        for k in kfs:
            for n in keys:
                if n in k and k["t"] <= t:
                    state[n] = float(k[n])
        for a, b in zip(kfs, kfs[1:]):
            if a["t"] <= t <= b["t"]:
                p = (t - a["t"]) / max(1e-6, b["t"] - a["t"])
                e = ease(b.get("ease", "easeInOutCubic"), p)
                out = {}
                for n in keys:
                    va = _last_value(kfs, a["t"], n, defaults[n], inclusive=True)
                    vb = float(b[n]) if n in b else va
                    out[n] = lerp(va, vb, e)
                return out
        return state


def _last_value(kfs, t, n, default, inclusive=True):
    v = default
    for k in kfs:
        if (k["t"] <= t if inclusive else k["t"] < t) and n in k:
            v = float(k[n])
    return v


class OverlayScene:
    """Background + layers + fx for one overlay scene. Time t is seconds since scene start."""

    def __init__(self, spec: dict, bg: Image.Image, layer_images: dict, w: int, h: int, style: dict):
        self.spec = spec
        self.bg = bg
        self.w, self.h = w, h
        self.layers = [Layer(l, layer_images[l["id"]], h) for l in spec["layers"]]
        self.by_id = {l.id: l for l in self.layers}
        self.fx = spec.get("fx", [])
        self.bg_motion = spec.get("background_motion", "push_in")
        self.style = style
        self.paper = _hex(style.get("post", {}).get("paper", "#000000"))
        self._cache: dict = {}

    # --- geometry of a layer at time t, in canvas pixels
    def geom(self, layer: Layer, t: float, depth: int = 0) -> dict:
        pr = layer.props_at(t)
        img = layer.image_at(t)
        hpx = layer.base_h * pr["scale"]
        wpx = img.width * hpx / max(1, img.height)
        x, y = pr["x"] * self.w, pr["y"] * self.h
        follow_pos = self._follow(layer, t, depth)
        if follow_pos is not None:
            x, y = follow_pos
        if layer.anchor == "bottom":
            left, top = x - wpx / 2, y - hpx
        else:
            left, top = x - wpx / 2, y - hpx / 2
        return {"img": img, "w": wpx, "h": hpx, "left": left, "top": top, "rot": pr["rot"],
                "opacity": pr["opacity"], "x": x, "y": y}

    def point(self, layer: Layer, t: float, name: str, depth: int) -> tuple[float, float]:
        g = self.geom(layer, t, depth + 1)
        cx = g["left"] + g["w"] / 2
        pts = {
            "top": (cx, g["top"]), "head": (cx, g["top"] + g["h"] * 0.02),
            "center": (cx, g["top"] + g["h"] / 2), "bottom": (cx, g["top"] + g["h"]),
            "hand_right": (g["left"] + g["w"] * 0.85, g["top"] + g["h"] * 0.45),
            "hand_left": (g["left"] + g["w"] * 0.15, g["top"] + g["h"] * 0.45),
        }
        if name not in pts:
            raise ValueError(f"Unknown follow point '{name}' (top, head, center, bottom, hand_left, hand_right)")
        return pts[name]

    def _follow(self, layer: Layer, t: float, depth: int):
        if not layer.follow or depth > 4:
            return None
        segs = layer.follow
        for s in segs:
            if s["from"] <= t <= s["to"]:
                tgt = self.by_id[s["layer"]]
                px, py = self.point(tgt, t, s.get("point", "top"), depth)
                return px + s.get("dx", 0) * self.h, py + s.get("dy", 0) * self.h
        for a, b in zip(segs, segs[1:]):  # hand-off between two follow segments
            if a["to"] < t < b["from"]:
                ta, tb = self.by_id[a["layer"]], self.by_id[b["layer"]]
                pa = self.point(ta, a["to"], a.get("point", "top"), depth)
                pb = self.point(tb, b["from"], b.get("point", "top"), depth)
                pa = (pa[0] + a.get("dx", 0) * self.h, pa[1] + a.get("dy", 0) * self.h)
                pb = (pb[0] + b.get("dx", 0) * self.h, pb[1] + b.get("dy", 0) * self.h)
                p = ease(b.get("ease", "easeInOutCubic"), (t - a["to"]) / (b["from"] - a["to"]))
                arc = math.sin(math.pi * p) * b.get("arc", 0.08) * self.h   # little lift while moving
                return lerp(pa[0], pb[0], p), lerp(pa[1], pb[1], p) - arc
        return None

    def _fx_state(self, t: float):
        dx = dy = 0.0
        flash = 0.0
        zoom_punch = 0.0
        for fx in self.fx:
            t0, dur = fx["t"], fx.get("duration", 0.3)
            if not (t0 <= t <= t0 + dur):
                continue
            k = 1 - (t - t0) / dur
            if fx["type"] == "shake":
                s = fx.get("strength", 14) * k
                rng = random.Random(int(t * 240))
                dx += rng.uniform(-s, s)
                dy += rng.uniform(-s, s)
            elif fx["type"] == "flash":
                flash = max(flash, fx.get("strength", 0.7) * k ** 2)
            elif fx["type"] == "zoom_punch":
                zoom_punch = max(zoom_punch, fx.get("strength", 0.05) * math.sin(math.pi * (1 - k)))
        return dx, dy, flash, zoom_punch

    def background(self, t: float, p: float, clip_len: float) -> Image.Image:
        dx, dy, _, punch = self._fx_state(t)
        z, cx, cy = camera(self.bg_motion, p, 1.0, (0.5, 0.5), 0.06, "easeInOutSine", clip_len)
        return view_transform(self.bg, self.w, self.h, z * (1 + punch), cx, cy, fill=self.paper,
                              dx_px=dx, dy_px=dy).convert("RGBA")

    def bg_is_steady(self, t0: float, t1: float) -> bool:
        for fx in self.fx:
            if fx["type"] in ("shake", "zoom_punch") and fx["t"] <= t1 and t0 <= fx["t"] + fx.get("duration", 0.3):
                return False
        return True

    def _layer_image(self, g: dict) -> Image.Image:
        w, h = max(1, int(round(g["w"]))), max(1, int(round(g["h"])))
        rot = round(g["rot"] * 4) / 4
        op = round(g["opacity"] * 50) / 50
        key = (id(g["img"]), w, h, rot, op)
        im = self._cache.get(key)
        if im is None:
            im = g["img"].resize((w, h), Image.Resampling.LANCZOS)
            if abs(rot) > 0.05:
                im = im.rotate(-rot, resample=Image.Resampling.BICUBIC, expand=True)
            if op < 1:
                im.putalpha(im.getchannel("A").point(lambda v, o=op: int(v * o)))
            if len(self._cache) > 96:
                self._cache.clear()
            self._cache[key] = im
        return im

    def composite(self, t: float, p: float, clip_len: float, bg: Optional[Image.Image] = None,
                  with_flash: bool = True) -> Image.Image:
        dx, dy, flash, _ = self._fx_state(t)
        frame = (bg if bg is not None else self.background(t, p, clip_len)).copy()
        for layer in self.layers:
            g = self.geom(layer, t)
            if g["opacity"] <= 0.003 or g["w"] < 2 or g["h"] < 2:
                continue
            im = self._layer_image(g)
            left = g["left"] + dx - (im.width - g["w"]) / 2
            top = g["top"] + dy - (im.height - g["h"]) / 2
            if layer.spec.get("shadow") and layer.kind == "character":
                self._shadow(frame, g, dx, dy)
            if layer.spec.get("glow"):
                glow = im.getchannel("A").filter(ImageFilter.GaussianBlur(14))
                col = Image.new("RGBA", im.size, _hex(layer.spec["glow"]) + (0,))
                col.putalpha(glow.point(lambda v: int(v * 0.8)))
                _paste(frame, col, left, top)
            _paste(frame, im, left, top)
        out = frame.convert("RGB")
        if with_flash and flash > 0:
            out = Image.blend(out, Image.new("RGB", out.size, (255, 255, 255)), min(1.0, flash))
        return out

    def flash_at(self, t: float) -> float:
        return self._fx_state(t)[2]

    def _shadow(self, frame: Image.Image, g: dict, dx: float, dy: float):
        sw, sh = g["w"] * 0.8, max(6, g["h"] * 0.05)
        layer = Image.new("L", (int(sw + 40), int(sh + 40)), 0)
        ImageDraw.Draw(layer).ellipse([20, 20, 20 + sw, 20 + sh], fill=int(110 * g["opacity"]))
        layer = layer.filter(ImageFilter.GaussianBlur(10))
        shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        shadow.putalpha(layer)
        x = g["left"] + g["w"] / 2 - layer.width / 2 + dx
        y = g["top"] + g["h"] - sh / 2 - 20 + dy
        _paste(frame, shadow, x, y)

    def motion_px(self, t0: float, t1: float) -> float:
        """Largest layer displacement between t0 and t1 (to decide on motion blur)."""
        m = 0.0
        for layer in self.layers:
            if not layer.spec.get("motion_blur", True):
                continue
            a, b = self.geom(layer, t0), self.geom(layer, t1)
            m = max(m, math.hypot(a["left"] - b["left"], a["top"] - b["top"]), abs(a["h"] - b["h"]))
        for fx in self.fx:
            if fx["type"] == "shake" and fx["t"] <= t1 and t0 <= fx["t"] + fx.get("duration", 0.3):
                m = max(m, 4.0)
        return m


# ----------------------------------------------------------------------------- render a cut

def render_cut(ffmpeg: str, out_path: str, *, w: int, h: int, fps: int, t_start: float, t_end: float,
               scene_start: float, image: Optional[Image.Image], style: dict, preset: Optional[str],
               variant: int, key: str, overlay: Optional[OverlayScene], render_cfg: dict) -> None:
    """Render timeline range [t_start, t_end] (includes transition handles) to out_path."""
    n = max(1, int(round((t_end - t_start) * fps)))
    clip_len = n / fps
    enc = Encoder(ffmpeg, out_path, w, h, fps, render_cfg.get("crf", 18), render_cfg.get("preset", "medium"),
                  vf=screen_fx_filter(style.get("frame_fx")))
    samples = int(render_cfg.get("motion_blur_samples", 8))
    shutter = float(render_cfg.get("shutter", 180)) / 360.0
    resample = Image.Resampling.BICUBIC if render_cfg.get("quality") == "high" else Image.Resampling.BILINEAR
    motion = style.get("motion", {})
    amount = float(motion.get("zoom", 0.08))
    easing = motion.get("ease", "easeInOutSine")
    base_zoom = VARIANT_ZOOM[variant % len(VARIANT_ZOOM)] if variant else 1.0
    focus = _focus_for(key, variant)
    fill = _hex(style.get("post", {}).get("paper", "#000000"))
    try:
        for i in range(n):
            p = (i + 0.5) / n
            t_local = t_start + (i + 0.5) / fps - scene_start
            if overlay is not None:
                span = shutter / fps
                t0, t1 = t_local - span / 2, t_local + span / 2
                moving = samples > 1 and overlay.motion_px(t0, t1) > 1.5
                if moving:
                    steady = overlay.bg_is_steady(t0, t1)
                    bg = overlay.background(t_local, p, clip_len) if steady else None
                    acc = None
                    for sidx in range(samples):
                        ts = t_local + span * ((sidx + 0.5) / samples - 0.5)
                        ps = p + (ts - t_local) / clip_len
                        fr = np.asarray(overlay.composite(ts, ps, clip_len, bg=bg, with_flash=False),
                                        dtype=np.float32)
                        acc = fr if acc is None else acc + fr
                    frame = Image.fromarray((acc / samples + 0.5).astype(np.uint8))
                    fl = overlay.flash_at(t_local)
                    if fl > 0:
                        frame = Image.blend(frame, Image.new("RGB", frame.size, (255, 255, 255)), min(1.0, fl))
                else:
                    frame = overlay.composite(t_local, p, clip_len)
            else:
                z, cx, cy = camera(preset, p, base_zoom, focus, amount, easing, clip_len)
                frame = view_transform(image, w, h, z, cx, cy, fill=fill, resample=resample)
            enc.write(frame)
    finally:
        enc.close()


def render_job(job: dict) -> str:
    """Process-pool entry point: everything is passed as plain data and files."""
    image = Image.open(job["image"]).convert("RGB")
    overlay = None
    if job.get("overlay"):
        layer_imgs = {lid: {k: Image.open(p).convert("RGBA") for k, p in imgs.items()}
                      for lid, imgs in job["layer_images"].items()}
        overlay = OverlayScene(job["overlay"], image, layer_imgs, job["w"], job["h"], job["style"])
    render_cut(job["ffmpeg"], job["tmp"], w=job["w"], h=job["h"], fps=job["fps"], t_start=job["t_start"],
               t_end=job["t_end"], scene_start=job["scene_start"], image=image, style=job["style"],
               preset=job["preset"], variant=job["variant"], key=job["key"], overlay=overlay,
               render_cfg=job["render"])
    import os
    os.replace(job["tmp"], job["out"])
    return job["out"]
