"""Voice catalogue: 25 female + 25 male Kokoro voices, with a short sample of each (voices/<name>.mp3)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

LANG = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "h": "hi", "i": "it", "j": "ja", "p": "pt-br", "z": "cmn"}
LANG_NAME = {"en-us": "English (US)", "en-gb": "English (UK)", "es": "Spanish", "fr-fr": "French", "hi": "Hindi",
             "it": "Italian", "ja": "Japanese", "pt-br": "Portuguese (BR)", "cmn": "Chinese"}

FEMALE = ("af_heart af_bella af_nicole af_sarah af_sky af_alloy af_aoede af_jessica af_kore af_nova af_river "
          "bf_emma bf_isabella bf_alice bf_lily ef_dora ff_siwis hf_alpha hf_beta if_sara pf_dora "
          "jf_alpha zf_xiaobei zf_xiaoxiao zf_xiaoyi").split()
MALE = ("am_michael am_adam am_echo am_eric am_fenrir am_liam am_onyx am_puck am_santa "
        "bm_george bm_lewis bm_daniel bm_fable em_alex em_santa hm_omega hm_psi im_nicola pm_alex pm_santa "
        "jm_kumo zm_yunjian zm_yunxi zm_yunxia zm_yunyang").split()

TEXT = {
    "en-us": "Long ago, the Greeks built a giant wooden horse and left it at the gates of Troy.",
    "en-gb": "Long ago, the Greeks built a giant wooden horse and left it at the gates of Troy.",
    "es": "Hace mucho tiempo, los griegos construyeron un enorme caballo de madera frente a las puertas de Troya.",
    "fr-fr": "Il y a très longtemps, les Grecs ont construit un immense cheval de bois devant les portes de Troie.",
    "hi": "बहुत समय पहले, यूनानियों ने ट्रॉय के द्वार पर एक विशाल लकड़ी का घोड़ा बनाया था।",
    "it": "Tanto tempo fa, i Greci costruirono un enorme cavallo di legno davanti alle porte di Troia.",
    "ja": "昔々、ギリシャ人はトロイの城門の前に大きな木馬を作りました。",
    "pt-br": "Há muito tempo, os gregos construíram um enorme cavalo de madeira diante dos portões de Troia.",
    "cmn": "很久以前，希腊人在特洛伊城门前造了一匹巨大的木马。",
}


def lang_for(voice: str) -> str:
    return LANG.get(voice[:1], "en-us")


def make_samples(settings, out_dir: str, ffmpeg: str = "ffmpeg") -> list[str]:
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro(settings.kokoro_model, settings.kokoro_voices)
    os.makedirs(out_dir, exist_ok=True)
    done = []
    for v in FEMALE + MALE:
        lang = lang_for(v)
        try:
            a, sr = k.create(TEXT[lang], voice=v, speed=1.0, lang=lang)
        except Exception as e:                               # a voice that will not speak is left out
            print(f"  skipped {v}: {e}")
            continue
        wav = Path(out_dir) / f"{v}.wav"
        sf.write(str(wav), np.asarray(a, dtype=np.float32), sr)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "64k", str(wav.with_suffix(".mp3"))],
                       check=True)
        wav.unlink()
        done.append(v)
    return done


def write_index(out_dir: str, done: list[str]) -> None:
    def rows(names):
        return "".join(
            f'<tr><td><b>{v}</b></td><td>{LANG_NAME[lang_for(v)]}</td>'
            f'<td><audio controls preload="none" src="{v}.mp3"></audio></td></tr>' for v in names if v in done)
    html = ('<!doctype html><meta charset="utf-8"><title>Voice samples</title>'
            '<style>body{font:16px system-ui;max-width:760px;margin:2em auto;padding:0 1em}td{padding:4px 12px}</style>'
            '<h1>Voice samples</h1><p>Use the name in <code>"voice": {"voice": "&lt;name&gt;"}</code> in project.json.</p>'
            f'<h2>Female</h2><table>{rows(FEMALE)}</table><h2>Male</h2><table>{rows(MALE)}</table>')
    (Path(out_dir) / "index.html").write_text(html, encoding="utf-8")
