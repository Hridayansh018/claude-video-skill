# vdo-skill: paste a script, get a video

A Claude skill plus a local video engine. You paste a script into Claude and get back a finished
1080p MP4 with captions:

- **Pictures:** Google Flow (Nano Banana) in a flat 2D cartoon, stick-figure history-explainer style,
  or an oil-painting style.
- **Characters and objects:** drawn in Google Flow on a flat green screen, cut out by the engine, and animated
  over the background: they pop in on the exact narration word, walk, run, talk (the mouth moves with the voice),
  gesture and leave. A recurring character keeps the same look in every scene.
- **Voice:** Kokoro, offline and free, with a natural British or American voice.
- **Sound:** generated background music that ducks under the voice, a soft sound-effect library (applause,
  cheer, scream, blast, fire, battle, thunder and about 40 more) triggered by what the narration says, and
  ambience beds. Scene-change and pop-up sounds are gentle.
- **Motion:** smooth pans and zooms, and transitions between scenes.
- **No AI video:** pictures only (no Veo), so there is no video watermark. The Flow corner mark is cropped out.

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
| **Google account** with access to **Google Flow** (flow.google.com) | pictures | no |

About 2 GB of free disk space is enough.

## 2. Run the setup (5–10 minutes)

1. Put this folder where you want it to stay, for example `D:\vdo-skill`. If you move
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
cd /d D:\vdo-skill
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

At the time of writing, Nano Banana pictures showed **0 credits** in Flow.

**About watermarks.** Flow stamps a small sparkle in the bottom-right corner of pictures on some plans. The
engine trims `corner_crop` (default 8%) off the right and bottom edges and zooms back to full frame, so it is
gone from the video. Characters and objects are cut out of their green screen, so the corner never reaches
them. If Flow offers a larger download (2K), use it: the crop then loses no sharpness. Google's invisible
SynthID mark is inside every Flow picture and cannot be removed; it is not visible.

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
a test"*, *"burn the captions in"* or *"make the music a bit louder"*.

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
```

`Popups` takes `name = description @ word it appears on`, separated by `;`. Add `(prop)` for objects.
A recurring character is listed once under `## Cast` and then used by name, with actions after `|`:

```markdown
## Cast
* socrates: an old bald stick figure philosopher with a big white beard, white toga, barefoot

* **Popups:** socrates @ Socrates | walks in from left | talks | points @ questions; scroll = a rolled scroll (prop) @ wrote
```

Actions: `walks in from left|right`, `runs in from ...`, `walks to centre|left|right @ word`, `leaves right @ word`,
`talks`, `points / cheers / waves / thinks / shocked / sad / angry / fights / bows / sits / kneels / falls @ word`.
Each pose is its own Flow picture, made with the character's master picture attached as a reference so the
face and clothes stay the same. Claude does this for you. See `examples/greece_sample.md`.

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
  "audio": {"music": "auto", "music_mood": "warm", "music_gain_db": -18},
  "corner_crop": 0.08,
  "subtitles": {"burn_in": false},
  "canvas": {"width": 1920, "height": 1080, "fps": 30}
}
```

- **Voices:** `bm_george`, `bm_lewis` (British male), `bf_emma` (British female), `am_michael` (US male) and
  `af_heart` (US female). There are 54 in total.
- **Music moods:** `warm`, `wonder` and `serious`. You can also give a path to your own music file, or
  `null` for no music.
- **Sound levels** (`"audio"` in project.json, dB): `music_gain_db` -18 (raise for louder music), `duck_db` -8
  (how far music drops under the voice), `sfx_gain_db` -6, `ambience_gain_db` -27, `transition_gain_db` 0,
  `event_gain_db` 0. `"transition_sfx": "auto"` is a soft airy swish; `"none"` removes it, or give a sound
  name. `"auto_events": false` stops narration-triggered effects, `"auto_ambience": false` the background beds.
- **Sound effects** (`vdo.bat sfx-list`): applause, cheer, celebration, chaos, scream, gasp, laugh, battle_burst,
  sword_clash, arrows, war_drums, war_horn, march, gallop, blast, explosion, fire_burst, thunder, earthquake,
  crash, splash, fanfare, bell, gong, coins, anvil, heartbeat, magic and more, plus ambience beds (crowd, battle,
  fire, market, rain, storm, sea, wind, night, forest, city, ...). All generated in code. Your own files in
  `sfx_library\<name>\` override a built-in. Use one with `**SFX:** blast @ exploded`, or let the narration
  trigger it ("the crowd cheered" plays a cheer).
- **Styles:** these live in `vdo/styles.json`. Each style has its prompt text, motion, transitions,
  caption font and sounds.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `doctor` shows `[!!] kokoro_onnx` or onnxruntime DLL errors | Install the VC++ runtime (`winget install Microsoft.VCRedist.2015+.x64`). If you're on Python 3.13+, install 3.12, delete `.venv` and run `setup.bat` again |
| `doctor` shows the Kokoro model missing | Run `setup.bat` again, or download the two files into `models\` (manual setup above) |
| `ffmpeg: MISSING` | `winget install Gyan.FFmpeg`, then open a new terminal. Or set `"ffmpeg_path"` in `config.json` (copy `config.example.json`) |
| Video won't play on Windows (0xC00D36C4) | Rebuild. The engine writes AAC at 48 kHz, which Windows players need |
| Green edge or box around a character | The green screen wasn't flat. Regenerate that picture or replace `images\<id>.jpg` |
| Build says pictures are missing | `vdo.bat status ...` lists them. Make them, or build with `--allow-missing` |
| Claude can't find pictures in Flow | Flow's page changed. Ask Claude to look at the page and adjust `flow/flow_helper.js` |
| Renders are slow | Use `--preview` while testing. Set `"render": {"workers": 4}` in project.json on a fast PC |

## Credits and licences

- Kokoro TTS by hexgrad, ONNX build by thewh1teagle (Apache-2.0).
- ffmpeg (LGPL/GPL).
- Music and sound effects are generated in code, so there is nothing to license.
- Pictures you make in Google Flow fall under Google's terms for Flow.
