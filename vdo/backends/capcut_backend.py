"""Push a finished vdo build into CapCut as an editable draft.

Uses the CapCutAPI code vendored in ../capcutapi (Apache-2.0, see capcutapi/NOTICE.md).

What lands in CapCut
- Video: every cut as its own clip on one track, exactly as the engine rendered it (pop-up characters, walking,
  pans and zooms, motion blur, shake), with the transition between scenes and pictures. You can trim, move or
  delete cuts, add your own clips, and re-time anything.
- Audio: voice, sound effects, ambience and music as separate tracks, so each can be turned up or down.
- Captions: a text track from the SRT, styled like the project's caption style (white_outline / yellow_pop /
  the picture style's own look), editable line by line.
- Pro-only CapCut effects are never used, so exporting stays free.

Where it goes
- Always: <project>/output/capcut_draft/<project name>   (a complete draft folder)
- When CapCut is installed (Windows: %LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft) and deploy is on:
  also copied there, so the project shows up in CapCut's project list.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from ..config import REPO_ROOT
from ..util import log

# engine transition name -> CapCut transition name (only free ones). Anything unknown becomes "Mix".
XFADE_TO_CAPCUT = {
    "fade": "Dissolve", "dissolve": "Dissolve", "fadefast": "Dissolve", "fadeslow": "Dissolve",
    "fadeblack": "Black_Fade", "fadewhite": "White_Flash", "fadegrays": "Dissolve",
    "wipeleft": "Wipe_Left", "wiperight": "Wipe_Right", "wipeup": "Wipe_Up",
    "slideleft": "Slide", "slideright": "Slide", "slideup": "Slide", "slidedown": "Slide",
    "smoothleft": "Slide", "smoothright": "Slide", "zoomin": "Pull_in", "hblur": "Horizontal_Blur",
    "radial": "Radial_Blur", "circleopen": "Mix", "circleclose": "Mix",
}

# caption looks: (fill colour, outline colour, outline width 0-100, size, bold)
CAPTION_LOOKS = {
    "yellow_pop": ((1.0, 0.898, 0.0), (0.0, 0.0, 0.0), 55.0, 9.0, True),
    "white_outline": ((1.0, 1.0, 1.0), (0.0, 0.0, 0.0), 70.0, 9.0, True),
}


def _quiet(fn, *a, **kw):
    """Run a CapCutAPI function without its progress prints."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def capcut_settings(b) -> dict:
    """Project "capcut" block layered over config.json's "capcut" block layered over defaults."""
    cfg = {"deploy": True, "profile": "jianying_pro_10", "is_capcut_env": True, "captions": True,
           "project_name": None, "close_app": False, "drafts_dir": None, "audio": True}
    cfg.update((b.settings.extra or {}).get("capcut", {}) or {})
    cfg.update(b.project.get("capcut", {}) or {})
    return cfg


def _import_capcutapi(profile: str, is_capcut_env: bool):
    root = REPO_ROOT / "capcutapi"
    if not (root / "save_draft_impl.py").exists():
        raise RuntimeError(f"The bundled CapCutAPI is missing at {root}. Re-download the project.")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        import settings.local as L
        import settings as S
    except ModuleNotFoundError as e:
        raise RuntimeError(f"Could not load CapCutAPI settings ({e}).")
    for mod in (L, S):                       # the add_* modules read these when they are first imported
        mod.DRAFT_PROFILE = profile
        mod.IS_CAPCUT_ENV = bool(is_capcut_env)
    try:
        import create_draft, add_audio_track, add_video_track, save_draft_impl  # noqa: F401
        import pyJianYingDraft as draft  # noqa: F401
    except ModuleNotFoundError as e:
        raise RuntimeError(f"CapCutAPI needs a package that is not installed: {e.name}. "
                           f"Run setup.bat again (or: pip install imageio requests psutil json5).")
    return create_draft, add_video_track, add_audio_track, save_draft_impl, draft


def drafts_dir(cfg: dict) -> Path | None:
    """CapCut's project folder on this computer, or None when CapCut is not installed."""
    if cfg.get("drafts_dir"):
        return Path(cfg["drafts_dir"])
    if os.name == "nt":
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        return p if p.exists() else None
    p = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    return p if p.exists() else None


def _capcut_running() -> bool:
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe"], capture_output=True, text=True).stdout
        return "CapCut.exe" in out
    except Exception:
        return False


def _caption_style(b):
    """(style name, Text_style kwargs, Text_border kwargs) for the project's caption style."""
    name = (b.project.get("subtitles") or {}).get("style", "scene")
    if name in CAPTION_LOOKS:
        fill, line, width, size, bold = CAPTION_LOOKS[name]
        return name, dict(color=fill, size=size, bold=bold), dict(color=line, width=width)
    st = b.styles.get(b.project.get("default_style") or "stickman").get("subtitle", {})
    return ("scene", dict(color=_hex_rgb(st.get("color", "#FFFFFF")), size=8.0, bold=bool(st.get("bold", 1))),
            dict(color=_hex_rgb(st.get("outline", "#000000")), width=45.0))


def export_capcut(b) -> str:
    cfg = capcut_settings(b)
    cd, avt, aat, sdi, draft = _import_capcutapi(cfg["profile"], cfg["is_capcut_env"])
    W, H = b.canvas["width"], b.canvas["height"]
    name = cfg["project_name"] or b.project["name"]
    cuts = b.plan["cuts"]
    draft_id, script = cd.get_or_create_draft(width=W, height=H)

    # ---- video: one clip per cut, with the transition into the next one
    for i, c in enumerate(b.clips):
        cut = c["cut"]
        if not os.path.exists(c["path"]):
            raise RuntimeError(f"Cut clip is missing: {c['path']} (build the video first)")
        nxt = cuts[i + 1]["transition_in"] if i + 1 < len(cuts) else None
        tr_name = tr_dur = None
        if nxt and nxt.get("duration", 0) > 0 and nxt.get("type") != "cut":
            tr_name = XFADE_TO_CAPCUT.get(nxt["type"], "Mix")
            tr_dur = float(nxt["duration"])
        slot = cut["end"] - cut["start"]
        kw = dict(video_url=c["path"], draft_id=draft_id, start=c["handle_in"], end=c["handle_in"] + slot,
                  target_start=cut["start"], width=W, height=H, track_name="main",
                  duration=c["t_end"] - c["t_start"], volume=0.0)
        try:
            _quiet(avt.add_video_track, transition=tr_name, transition_duration=tr_dur, **kw)
        except ValueError:                      # a transition name this CapCut build does not have
            _quiet(avt.add_video_track, **kw)
    log(f"  {len(b.clips)} clip(s) on the video track")

    # ---- audio: the engine's own stems, so every bus stays adjustable
    total = b.plan["duration"]
    if cfg.get("audio", True):
        for bus in ("voice", "sfx", "amb", "music"):
            wav = (b.stems or {}).get(bus)
            if not wav or not os.path.exists(wav):
                continue
            mp3 = os.path.splitext(wav)[0] + ".mp3"          # CapCutAPI stores audio as .mp3
            if not os.path.exists(mp3) or os.path.getmtime(mp3) < os.path.getmtime(wav):
                b.ff.run(["-i", wav, "-c:a", "libmp3lame", "-b:a", "192k", mp3])
            _quiet(aat.add_audio_track, audio_url=mp3, start=0, end=total, target_start=0, draft_id=draft_id,
                                volume=1.0, track_name=f"audio_{bus}", duration=total)
        log("  voice / effects / ambience / music tracks added")

    # ---- captions
    if cfg.get("captions", True) and b.srt and os.path.exists(b.srt):
        sname, tkw, bkw = _caption_style(b)
        try:
            script.import_srt(Path(b.srt).read_text(encoding="utf-8"), track_name="captions",
                              text_style=draft.Text_style(align=1, **tkw),
                              clip_settings=draft.Clip_settings(transform_y=-0.78),
                              border=draft.Text_border(alpha=1.0, **bkw))
            log(f"  captions added ({sname})")
        except Exception as e:
            log(f"  captions not added to the CapCut draft ({e})")

    # ---- save the draft folder next to the video, then register it with CapCut
    out_root = b.out_dir / "capcut_draft"
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    res = _quiet(sdi.save_draft_impl, draft_id=draft_id, draft_folder=str(out_root), project_name=None, auto_deploy=False)
    if not res or not res.get("success") or not res.get("draft_url"):
        raise RuntimeError(f"CapCutAPI could not save the draft ({res}). See the log above for the error.")
    built = Path(res["draft_url"])
    final = out_root / name
    if final.exists():
        shutil.rmtree(final)
    built.rename(final)
    _rewrite_material_paths(final)
    log(f"  draft folder: {final}")

    target = drafts_dir(cfg) if cfg.get("deploy", True) else None
    if target is None:
        log("  CapCut's project folder was not found, so the draft was not copied in. "
            "Copy the folder above into CapCut's project folder, or set capcut.drafts_dir.")
        return str(final)
    if _capcut_running():
        if cfg.get("close_app"):
            log("  closing CapCut so it does not overwrite the new draft")
            subprocess.run(["taskkill", "/IM", "CapCut.exe", "/F"], capture_output=True)
        else:
            log("  CapCut is open, so the draft was NOT copied in (it could be overwritten). Close CapCut and run "
                "`vdo.bat capcut <project.json>` again, or add --close-capcut to let me close it.")
            return str(final)
    dest = target / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(final, dest)
    (dest / ".locked").unlink(missing_ok=True)
    try:
        _register_with_capcut(b, cfg, target, name, total)
    except Exception as e:
        log(f"  CapCut registration step skipped ({e}); the draft may need a restart of CapCut to appear")
    log(f"  pushed to CapCut: {dest}")
    return str(dest)


def _rewrite_material_paths(proj: Path) -> None:
    """Point every video / audio material at the file inside this draft folder (the folder was renamed)."""
    posix_proj = proj.as_posix()
    files = {}
    for sub in ("audio", "image", "video"):
        d = proj / "assets" / sub
        if d.exists():
            for fn in os.listdir(d):
                files[fn] = f"{posix_proj}/assets/{sub}/{fn}"
    for rel in ("draft_content.json", "draft_content.json.bak", "template-2.tmp"):
        f = proj / rel
        if not f.exists() or not f.stat().st_size:
            continue
        cur = json.loads(f.read_text(encoding="utf-8"))
        for kind in ("videos", "audios"):
            for m in cur.get("materials", {}).get(kind, []):
                fn = os.path.basename(m.get("path", "").replace("\\", "/"))
                m["path"] = files.get(fn, m.get("path", "").replace("\\", "/"))
        f.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


def _register_with_capcut(b, cfg: dict, base: Path, name: str, total: float) -> None:
    """Make CapCut list the draft: cover picture, absolute material paths, entry in root_meta_info.json.
    (Generalised from the 'CapCut 9.6 compatibility patch' used with CapCutAPI.)"""
    proj = base / name
    posix_base, posix_proj = base.as_posix(), proj.as_posix()
    cover = next((c.get("image") for c in b.clips if c.get("image")), None)
    if cover and os.path.exists(cover):
        shutil.copyfile(cover, proj / "draft_cover.jpg")
    content_path = proj / "draft_content.json"
    cur = json.loads(content_path.read_text(encoding="utf-8"))
    cur["new_version"] = str(cfg.get("new_version", "189.0.0"))
    cur["draft_type"] = "video"
    cur["color_space"] = -1
    W, H = b.canvas["width"], b.canvas["height"]
    cur["canvas_config"] = {"height": H, "width": W, "ratio": "16:9" if W > H else "9:16" if H > W else "1:1"}
    files = {}
    for sub in ("audio", "image", "video"):
        d = proj / "assets" / sub
        if d.exists():
            for fn in os.listdir(d):
                files[fn] = f"{posix_proj}/assets/{sub}/{fn}"
    for kind in ("videos", "audios"):
        for m in cur.get("materials", {}).get(kind, []):
            fn = os.path.basename(m.get("path", "").replace("\\", "/"))
            m["path"] = files.get(fn, m.get("path", "").replace("\\", "/"))
    text = json.dumps(cur, ensure_ascii=False, indent=2)
    for fn in ("draft_content.json", "draft_content.json.bak", "template-2.tmp"):
        (proj / fn).write_text(text, encoding="utf-8")
    tl_dir = proj / "Timelines"
    if tl_dir.exists():
        subs = [d for d in tl_dir.iterdir() if d.is_dir()]
        if subs:
            if cover and os.path.exists(cover):
                shutil.copyfile(cover, subs[0] / "draft_cover.jpg")
            for fn in ("draft_content.json", "draft_content.json.bak", "template-2.tmp", "template.tmp"):
                (subs[0] / fn).write_text(text, encoding="utf-8")
    meta_path = proj / "draft_meta_info.json"
    draft_id = ""
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not meta.get("draft_id"):
            meta["draft_id"] = str(uuid.uuid4()).upper()
        draft_id = meta["draft_id"]
        meta.update({"draft_name": name, "draft_root_path": posix_base, "draft_fold_path": posix_proj,
                     "draft_cover": "draft_cover.jpg", "tm_duration": int(total * 1e6), "draft_type": "video",
                     "draft_new_version": cur["new_version"]})
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    root_meta = base / "root_meta_info.json"
    if not root_meta.exists():
        return
    rm = json.loads(root_meta.read_text(encoding="utf-8"))
    entry_update = {"draft_root_path": posix_base, "draft_fold_path": posix_proj,
                    "draft_json_file": f"{posix_proj}/draft_content.json",
                    "draft_cover": f"{posix_proj}/draft_cover.jpg", "draft_type": "video",
                    "draft_new_version": cur["new_version"], "tm_duration": int(total * 1e6)}
    matched = False
    for item in rm.get("all_draft_store", []):
        if item.get("draft_name") == name:
            matched = True
            item.update(entry_update)
    if not matched:
        import time
        now_us = int(time.time() * 1e6)
        new_entry = {
            "cloud_draft_cover": False, "cloud_draft_sync": False, "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "", "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "", "draft_id": draft_id or str(uuid.uuid4()).upper(),
            "draft_is_ai_shorts": False, "draft_is_cloud_temp_draft": False, "draft_is_infinite_canvas_draft": False,
            "draft_is_invisible": False, "draft_is_pippit_draft": False, "draft_is_web_article_video": False,
            "draft_name": name, "draft_timeline_materials_size": 0, "draft_web_article_video_enter_from": "",
            "pippit_avatar_url": "", "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
            "streaming_edit_draft_ready": True, "tm_draft_cloud_completed": "", "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0, "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1, "tm_draft_create": now_us, "tm_draft_modified": now_us,
            "tm_draft_removed": 0, **entry_update,
        }
        rm.setdefault("all_draft_store", []).insert(0, new_entry)
    root_meta.write_text(json.dumps(rm, ensure_ascii=False), encoding="utf-8")
