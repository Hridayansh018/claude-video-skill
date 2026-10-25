# vdo-skill: paste a script, get a video

A Claude skill plus a local video engine. You paste a script into Claude and get back a finished
1080p MP4 with captions:

- **Pictures:** Google Flow (Nano Banana) in a flat 2D cartoon, stick-figure history-explainer style,
  or an oil-painting style.
- **Pop-ups:** characters and objects pop in over the background on the exact narration word, with
  motion blur, a whoosh and a pop.
- **Voice:** Kokoro, offline and free, with a natural British or American voice.
- **Sound:** generated background music that ducks under the voice, plus sound effects and ambience.
- **Motion:** smooth pans and zooms, and transitions between scenes.
- **Video clips (optional):** Veo clips from Flow for scenes that need real movement.

```
vdo-skill/
  setup.bat            one-click setup (Windows)      setup.sh   (macOS / Linux)
  vdo.bat              the engine command             vdo.sh
  skill/vdo-video/     SKILL.md: Claude's instructions (setup installs it)
  vdo/                 engine (Python)
  flow/flow_helper.js  small script Claude runs inside the Google Flow page
  models/              Kokoro voice model (downloaded by setup)
  projects/            one folder per video (script, pictures, output)
  examples/            sample script
```

---

## 1. What you need

| Tool | Why | Installed by setup.bat? |
|---|---|---|
| Windows 10/11 (or macOS / Linux) | | – |
| **Python 3.10 – 3.12** (3.12 recommended) | runs the engine | yes, via winget if missing |
| **ffmpeg** | video encoding | yes (winget `Gyan.FFmpeg`), with a fallback copy if winget can't |
| Python packages: numpy, pillow, scipy, soundfile, kokoro-onnx, onnxruntime, imageio-ffmpeg, edge-tts | engine, voice, audio | yes, into `.venv` |
| **Kokoro voice model** (`kokoro-v1.0.onnx` ~310 MB, `voices-v1.0.bin` ~27 MB) | offline narration | yes, into `models\` |
| **Claude**: Claude Code or the Claude desktop app | runs the skill | no, see step 3 |
| **A browser Claude can drive**: the Claude desktop app's built-in browser, or **Claude in Chrome** | makes pictures in Google Flow | no, see step 4 |
| **Google account** with access to **Google Flow** (flow.google.com) | pictures (and optional Veo clips) | no |

About 2 GB of free disk space is enough.

## 2. Run the setup (5–10 minutes)

1. Put this folder where you want it to stay, for example `C:\Users\<you>\Desktop\vdo-skill`. If you move
   it later, run setup again.
2. Double-click **`setup.bat`**. It runs six steps, and you can run it again at any time:

   1. **Python:** finds Python 3.10–3.12, or installs 3.12 with `winget`.
   2. **ffmpeg:** finds it, or installs it with `winget install Gyan.FFmpeg`.
   3. **Packages:** creates `.venv` and installs `requirements.txt` into it.
   4. **Voice model:** downloads the Kokoro model into `models\`.
   5. **Skill:** installs it to `%USERPROFILE%\.claude\skills\vdo-video\SKILL.md` (Claude Code), with this
      folder's path filled in. It also builds `dist\vdo-video-skill.zip` to upload to the Claude app.
   6. **Check:** runs `vdo.bat doctor`, which should end with *Everything needed is installed.*

3. Test render, with no Claude or browser needed, using the sample pictures included:

   ```
   vdo.bat build projects\greece_sample\project.json
   ```

   The result is `projects\greece_sample\output\greece_sample.mp4` (40 seconds, three scenes, with pop-ups in
   scene 2).

On macOS or Linux run `./setup.sh` instead. Install ffmpeg first with `brew install ffmpeg` or
`sudo apt install ffmpeg`.

### Manual setup (if setup.bat can't do a step)

```bat
:: Python 3.12  -  https://www.python.org/downloads/  (tick "Add python.exe to PATH")
winget install -e --id Python.Python.3.12
:: ffmpeg
winget install -e --id Gyan.FFmpeg
:: packages
cd /d C:\Users\<you>\Desktop\vdo-skill
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
:: voice model (two files into models\)
curl -L -o models\kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o models\voices-v1.0.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
:: check
vdo.bat doctor
```

For the skill, copy `skill\vdo-video\SKILL.md` to `%USERPROFILE%\.claude\skills\vdo-video\SKILL.md`. Then
replace every `{{VDO_HOME}}` in the copy with this folder's full path.

## 3. Add the skill to Claude

Pick the one you use:

- **Claude Code** (terminal, or the desktop app's Code tab): `setup.bat` already installed the skill at
  `%USERPROFILE%\.claude\skills\vdo-video`. Start Claude Code from any folder, and `/skills` should list
  **vdo-video**. Claude Code runs the engine directly on your PC.
- **Claude desktop app / claude.ai**: open **Settings → Capabilities → Skills → Upload skill** and choose
  `dist\vdo-video-skill.zip`. For Claude to run the engine on your PC, the chat has to be able to use your
  computer. That means a Code session on your PC, or a chat linked to your computer with this folder
  connected. Otherwise Claude copies the engine into its own workspace and sends you the video when it's
  done (slower, but it works).

## 4. Let Claude make pictures in Google Flow

1. Sign in to your Google account at https://flow.google.com once in the browser Claude will use, and
   accept Flow's terms yourself.
2. Give Claude a browser:
   - **Claude desktop app:** use its built-in browser pane. Claude opens Flow there, and you sign in there once.
   - **Claude in Chrome:** install the extension from the Chrome Web Store, sign in, and allow it on
     `flow.google.com`. With Claude Code, start it with `claude --chrome`, or turn Chrome on in `/config`.
3. When Claude downloads the pictures the first time, Chrome may ask *"This site is trying to download
   multiple files"*. Click **Allow**. The files are named `vdo__<project>__<id>.jpg` and are moved out of
   Downloads straight away.

At the time of writing, Nano Banana pictures showed **0 credits** in Flow. Veo video clips cost credits and
carry a visible watermark unless your plan removes it. They are only used if you ask for them.

## 5. Make a video

In Claude, paste your script and say for example:

> make a video of this script (stick-figure style)

Claude then:

1. Saves the script and runs `vdo.bat new`.
2. Adds pop-ups for the characters and objects the narration introduces.
3. Runs `vdo.bat plan`, which voices the script, works out the timing and writes the picture prompts.
4. Rewrites each picture prompt to match the narration at that moment.
5. Makes every picture in Google Flow and imports them.
6. Runs `vdo.bat build` and tells you where the MP4 is.

A 5-minute script takes about 40–60 pictures and 15–25 minutes to render.

You can say things like *"use a female voice"*, *"oil painting style for scenes 3–5"*, *"only scenes 1–5 as
a test"*, *"burn the captions in"* or *"make scene 4 a Veo clip"*.

### Script format

Anything works. Plain paragraphs become one scene each. This format gives the most control:

```markdown
#### Scene 2 (0:12 – 0:26)
* **Voiceover:** Down in the busy marketplace, a barefoot old man named Socrates ...
* **Video Prompt:** The ancient Athenian agora marketplace in warm afternoon light ...
* **Popups:** socrates = an old barefoot bearded philosopher in a white toga @ Socrates; scroll = a rolled parchment scroll (prop) @ wrote
* **SFX:** crowd
* **Style:** oil            (optional, per scene)
* **Images:** 2             (optional, pictures for this scene)
* **Clip:** clips/s02.mp4   (optional, a video clip instead of pictures)
```

`Popups` takes `name = description @ word it appears on`, separated by `;`. Add `(prop)` for objects.
See `examples/greece_sample.md`.

## 6. Using the engine by hand

```bat
vdo.bat new  my_script.md --name egypt [--scenes 1-5] [--style oil] [--image-duration 6]
vdo.bat plan   projects\egypt\project.json   :: voice + timing + image_prompts.md / image_jobs.json
:: make each picture in images\ with the file name image_prompts.md gives (s01_1.jpg, s02_bg.jpg, ...)
vdo.bat status projects\egypt\project.json   :: what is still missing
vdo.bat import projects\egypt\project.json   :: move Flow downloads (vdo__egypt__<id>.jpg) into images\
vdo.bat sheet  projects\egypt\project.json   :: contact_sheet.jpg of all pictures
vdo.bat build  projects\egypt\project.json [--preview] [--allow-missing]
vdo.bat sfx-list                              :: available sound names
vdo.bat doctor                                :: check the setup
```

`project.json` holds every setting. Common ones:

```json
{
  "voice": {"voice": "bm_george", "speed": 1.0},
  "image_duration": 6.0,
  "audio": {"music": "auto", "music_mood": "warm", "music_gain_db": -21},
  "subtitles": {"burn_in": false},
  "canvas": {"width": 1920, "height": 1080, "fps": 30}
}
```

- **Voices:** `bm_george`, `bm_lewis` (British male), `bf_emma` (British female), `am_michael` (US male) and
  `af_heart` (US female). There are 54 in total.
- **Music moods:** `warm`, `wonder` and `serious`. You can also give a path to your own music file, or
  `null` for no music.
- **Styles:** these live in `vdo/styles.json`. Each style has its prompt text, motion, transitions,
  caption font and sounds.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `doctor` shows `[!!] kokoro_onnx` or onnxruntime DLL errors | Install the VC++ runtime (`winget install Microsoft.VCRedist.2015+.x64`). If you're on Python 3.13+, install 3.12, delete `.venv` and run `setup.bat` again |
| `doctor` shows the Kokoro model missing | Run `setup.bat` again, or download the two files into `models\` (manual setup above) |
| `ffmpeg: MISSING` | `winget install Gyan.FFmpeg`, then open a new terminal. Or set `"ffmpeg_path"` in `config.json` (copy `config.example.json`) |
| Video won't play on Windows (0xC00D36C4) | Rebuild. The engine writes AAC at 48 kHz, which Windows players need |
| White box around a pop-up character | The picture didn't have a plain white background. Regenerate it, or replace `images\<id>.jpg` |
| Build says pictures are missing | `vdo.bat status ...` lists them. Make them, or build with `--allow-missing` |
| Claude can't find pictures in Flow | Flow's page changed. Ask Claude to look at the page and adjust `flow/flow_helper.js` |
| Renders are slow | Use `--preview` while testing. Set `"render": {"workers": 4}` in project.json on a fast PC |

## Credits and licences

- Kokoro TTS by hexgrad, ONNX build by thewh1teagle (Apache-2.0).
- ffmpeg (LGPL/GPL).
- Music and sound effects are generated in code, so there is nothing to license.
- Pictures and clips you make in Google Flow fall under Google's terms for Flow.
