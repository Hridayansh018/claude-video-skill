# claude-video-skill: paste a script, get a video

A Claude skill plus a local video engine. You paste a script into Claude and get back a finished
MP4 (1080p, or 2K with one flag) with captions:

- **Pictures:** Google Flow (Nano Banana) in a flat 2D cartoon, stick-figure history-explainer style,
  or an oil-painting style.
- **Characters and objects:** drawn in Google Flow on a flat green screen, cut out by the engine, and animated
  over the background: they pop in on the exact narration word, walk, run, talk (the mouth moves with the voice),
  gesture and leave. A recurring character keeps the same look in every scene.
- **Voice:** Kokoro, offline and free, with a natural British or American voice.
- **Music:** generated, matched to the story (war, calm, epic, tense, dark, sad, triumph, mystery, adventure,
  wonder), changing between scenes when the story does, and ducking under the voice.
- **Sound effects:** real CC0 recordings from SFXMint (bundled starter pack) placed at the right moment from what the
  narration says, plus quiet ambience for places and weather. Scene-change and pop-up sounds are gentle.
- **Captions:** an SRT file always, and optionally burned in with two styles: white text with a thick black
  outline, or yellow text with a black outline and shadow (see **Captions** below).
- **Export size:** 720p, 1080p, 2K (2560x1440) or 4K.
- **Motion:** smooth pans and zooms, and transitions between scenes.
- **No AI video:** pictures only (no Veo), so there is no video watermark. The Flow corner mark is cropped out.

```
claude-video-skill/
  setup.bat            one-click setup (Windows)      setup.sh   (macOS / Linux)
  vdo.bat              the engine command             vdo.sh
  skill/claude-video-skill/     SKILL.md: Claude's instructions (setup installs it)
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

1. Put this folder where you want it to stay, for example `D:\claude-video-skill`. If you move
   it later, run setup again.
2. Double-click **`setup.bat`**. It runs six steps, and you can run it again at any time:

   1. **Python:** finds Python 3.10–3.12, or installs 3.12 with `winget`.
   2. **ffmpeg:** finds it, or installs it with `winget install Gyan.FFmpeg`.
   3. **Packages:** creates `.venv` and installs `requirements.txt` into it.
   4. **Voice model:** downloads the Kokoro model into `models\`.
   5. **Skill:** installs it to `%USERPROFILE%\.claude\skills\claude-video-skill\SKILL.md` (Claude Code), with this
      folder's path filled in. It also builds `dist\claude-video-skill.zip` to upload to the Claude app.
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
cd /d D:\claude-video-skill
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
:: voice model (two files into models\)
curl -L -o models\kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o models\voices-v1.0.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
:: check
vdo.bat doctor
```

For the skill, copy `skill\claude-video-skill\SKILL.md` to `%USERPROFILE%\.claude\skills\claude-video-skill\SKILL.md`. Then
replace every `{{VDO_HOME}}` in the copy with this folder's full path.

## 3. Add the skill to Claude

### Quick start: paste this into Claude

Open Claude Code (or a chat linked to your computer) and paste the prompt below. Change the folder if you put
the engine somewhere else. Claude does the rest and tells you if anything needs you.

```text
Set up claude-video-skill for me.
1. The engine is in D:\vdo-skill. Run "D:\vdo-skill\vdo.bat doctor". If anything shows [!!], run setup.bat in
   that folder (or tell me to double-click it), then run doctor again until everything is [ok].
2. Make sure the skill is installed (setup.bat does it) and that /skills lists claude-video-skill.
3. Open https://flow.google.com in your browser. If it asks me to sign in, wait and tell me.
   Check the settings chip shows Image, Nano Banana, x1, 16:9.
4. Make a 10-second test video from a 2-scene script about any topic, with --res 1080p and
   --captions yellow_pop, so we know voice, pictures, music, captions and render all work.
5. Tell me where the MP4 is, and anything that failed.
From now on, when I paste a script and ask for a video, follow the claude-video-skill instructions end to end.
```

If you use the desktop app or claude.ai instead, upload the skill first (second option below), link the chat to
your computer with this folder connected, then paste the same prompt.


Pick the one you use:

- **Claude Code** (terminal, or the desktop app's Code tab): `setup.bat` already installed the skill at
  `%USERPROFILE%\.claude\skills\claude-video-skill`. Start Claude Code from any folder, and `/skills` should list
  **claude-video-skill**. Claude Code runs the engine directly on your PC.
- **Claude desktop app / claude.ai**: open **Settings → Capabilities → Skills → Upload skill** and choose
  `dist\claude-video-skill.zip`. For Claude to run the engine on your PC, the chat has to be able to use your
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

### Ask for each feature in plain words

Add any of these to the request. Claude turns them into the settings shown.

| You say | What Claude sets |
|---|---|
| "in 2K" / "export 2560x1440" | `"resolution": "2k"` (or `vdo.bat build ... --res 2k`) |
| "with yellow captions" | `"subtitles": {"burn_in": true, "style": "yellow_pop"}` |
| "with white outlined captions" | `"subtitles": {"burn_in": true, "style": "white_outline"}` |
| "no burned-in captions, just the SRT" | `"subtitles": {"burn_in": false}` (the `.srt` is always written) |
| "use the voice bf_emma" / "a deep male voice" | `"voice": {"voice": "bf_emma"}` (Claude offers 3 names from the Voices list) |
| "make it a war story" / "mysterious music" | `"story_type": "war"` / `"mystery"` (or `**Story Type:**` in the script) |
| "make the music quieter" | `"audio": {"music_gain_db": -18}` |
| "no sound effects" | `"audio": {"auto_events": false, "auto_ambience": false}` |
| "have Socrates walk in and point at the map" | a `## Cast` entry plus a `**Popups:**` line |
| "preview first" | `vdo.bat build ... --preview` (half size, quick) |


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

## Autopilot (one message, finished video)

Give Claude a video link, a topic or a script, plus a title or project name and a length, for example:

```text
Make a 5-minute video. Source: https://youtu.be/XXXX  (or: topic / pasted script)
Title idea: The Dancing Plague of 1518. Save to D:\vdo-skill\projects. Do not stop until it is done.
```

Claude then runs everything without asking to continue: script, project, pictures in Google Flow (built-in
browser), build in 2K with burned-in captions, the package (5 titles, thumbnail idea, description with chapters and
sources) and delivery of the MP4, SRT and `package.md`. It stops only if blocked (for example Google asks you to sign
in) or if you say "stop". Defaults you can change in the same message: voice `bm_george`, `2k`, captions
`yellow_pop`, story type `auto`. `vdo.bat chapters projects\<name>\project.json` writes the chapter lines from the
final timings.

## 6. Using the engine by hand

```bat
vdo.bat new  my_script.md --name egypt [--scenes 1-5] [--style oil] [--image-duration 6]
vdo.bat plan   projects\egypt\project.json   :: voice + timing + image_prompts.md / image_jobs.json
:: make each picture in images\ with the file name image_prompts.md gives (s01_1.jpg, s02_bg.jpg, ...)
vdo.bat status projects\egypt\project.json   :: what is still missing
vdo.bat import projects\egypt\project.json   :: move Flow downloads (vdo__egypt__<id>.jpg) into images\
vdo.bat sheet  projects\egypt\project.json   :: contact_sheet.jpg of all pictures
vdo.bat build  projects\egypt\project.json [--preview] [--allow-missing] [--res 2k] [--captions yellow_pop]
vdo.bat chapters projects\egypt\project.json :: YouTube chapter lines from the final timings
vdo.bat sfx-list                              :: available sound names
vdo.bat doctor                                :: check the setup
```

`project.json` holds every setting. Common ones:

```json
{
  "voice": {"voice": "bm_george", "speed": 1.0},
  "image_duration": 6.0,
  "audio": {"music": "auto", "music_mood": "auto", "music_gain_db": -15},
  "story_type": "auto",
  "corner_crop": 0.08,
  "subtitles": {"burn_in": true, "style": "yellow_pop"},
  "resolution": "2k",
  "canvas": {"fps": 30}
}
```

- **Voices:** 50 to choose from, each with a playable sample: see **Voices** below.
- **Story type and music:** `"story_type": "auto"` reads the script. Set it yourself with `"war"`, `"calm"`,
  `"epic"` (cinematic), `"tense"`, `"dark"`, `"sad"`, `"triumph"`, `"mystery"`, `"adventure"`, `"wonder"` or
  `"warm"`, or write `**Story Type:** war` at the top of the script. A scene can override it with
  `"mood": "tense"` or `**Mood:** tense`. `"audio": {"music_mood": "epic"}` keeps one style for the whole video.
  You can also give a path to your own music file, or `null` for no music.
- **Sound levels** (`"audio"` in project.json, dB): `music_gain_db` -15 (raise for louder music), `duck_db` -8
  (how far music drops under the voice), `sfx_gain_db` -6, `ambience_gain_db` -21, `transition_gain_db` 0,
  `event_gain_db` 0. `"transition_sfx": "auto"` is a soft airy swish; `"none"` removes it, or give a sound
  name. `"auto_events": false` stops narration-triggered effects, `"auto_ambience": false` the background beds.
- **Sound effects** (`vdo.bat sfx-list`): real recordings from SFXMint (CC0, free, no key) for blast, thunder,
  sword_clash, cheer, applause, scream, gasp, arrows, gallop, war_drums, fanfare, bell, gong, coins and more, and
  beds for fire, wind, rain, sea, cave and countryside. Other names are generated in code. `vdo.bat sfx-fetch`
  downloads any pack sound that is missing; `"sfx_source": "builtin"` turns real sounds off. Your own files in
  `sfx_library\<name>\` override both. Use one with `**SFX:** blast @ exploded`, or let the narration trigger it
  ("the crowd cheered" plays a cheer).
- **Captions:** an `.srt` file is always written next to the MP4. To burn captions into the picture set
  `"subtitles": {"burn_in": true, "style": "..."}` or build with `--captions <style>` (which also turns burn-in on).
  Styles: `white_outline` (white capitals, thick black outline), `yellow_pop` (yellow capitals, black outline,
  drop shadow, quick pop-in at the start of each caption), `scene` (the default: each picture style's own look from
  `styles.json`). Other options: `max_words` (7) and `max_chars` (42) per caption. Both presets use Arial Black
  (on Windows); if your machine lacks it, the closest bold font is used.
- **Export size:** `"resolution": "2k"` (2560x1440), or `720p`, `1080p` (default), `4k`; or `vdo.bat build ... --res 2k`.
  Bigger sizes use a cleaner encode (lower CRF) and take roughly twice as long at 2K. Flow's pictures are
  1376x768 and are scaled up smoothly, so use Flow's 2K upscale for backgrounds and scene pictures when offered.
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
- Music is generated in code, so there is nothing to license. Sound effects from SFXMint are CC0 (public domain); the rest are generated.
- Pictures you make in Google Flow fall under Google's terms for Flow.

## Voices (50 samples)

Every voice below has a short sample you can play. Open `voices/index.html` in a browser for players you can click through, or click a link here. Use the name in project.json: `"voice": {"voice": "bf_emma"}`. The language is picked from the voice automatically, and the voice speaks the language of the script (the samples read a Troy sentence in each voice's own language).

To remake the samples: `vdo.bat voices`.

### Female (25)

| Voice | Language | Sample |
|---|---|---|
| `af_heart` | English (US) | [▶ play](voices/af_heart.mp3) |
| `af_bella` | English (US) | [▶ play](voices/af_bella.mp3) |
| `af_nicole` | English (US) | [▶ play](voices/af_nicole.mp3) |
| `af_sarah` | English (US) | [▶ play](voices/af_sarah.mp3) |
| `af_sky` | English (US) | [▶ play](voices/af_sky.mp3) |
| `af_alloy` | English (US) | [▶ play](voices/af_alloy.mp3) |
| `af_aoede` | English (US) | [▶ play](voices/af_aoede.mp3) |
| `af_jessica` | English (US) | [▶ play](voices/af_jessica.mp3) |
| `af_kore` | English (US) | [▶ play](voices/af_kore.mp3) |
| `af_nova` | English (US) | [▶ play](voices/af_nova.mp3) |
| `af_river` | English (US) | [▶ play](voices/af_river.mp3) |
| `bf_emma` | English (UK) | [▶ play](voices/bf_emma.mp3) |
| `bf_isabella` | English (UK) | [▶ play](voices/bf_isabella.mp3) |
| `bf_alice` | English (UK) | [▶ play](voices/bf_alice.mp3) |
| `bf_lily` | English (UK) | [▶ play](voices/bf_lily.mp3) |
| `ef_dora` | Spanish | [▶ play](voices/ef_dora.mp3) |
| `ff_siwis` | French | [▶ play](voices/ff_siwis.mp3) |
| `hf_alpha` | Hindi | [▶ play](voices/hf_alpha.mp3) |
| `hf_beta` | Hindi | [▶ play](voices/hf_beta.mp3) |
| `if_sara` | Italian | [▶ play](voices/if_sara.mp3) |
| `pf_dora` | Portuguese (BR) | [▶ play](voices/pf_dora.mp3) |
| `jf_alpha` | Japanese | [▶ play](voices/jf_alpha.mp3) |
| `zf_xiaobei` | Chinese | [▶ play](voices/zf_xiaobei.mp3) |
| `zf_xiaoxiao` | Chinese | [▶ play](voices/zf_xiaoxiao.mp3) |
| `zf_xiaoyi` | Chinese | [▶ play](voices/zf_xiaoyi.mp3) |

### Male (25)

| Voice | Language | Sample |
|---|---|---|
| `am_michael` | English (US) | [▶ play](voices/am_michael.mp3) |
| `am_adam` | English (US) | [▶ play](voices/am_adam.mp3) |
| `am_echo` | English (US) | [▶ play](voices/am_echo.mp3) |
| `am_eric` | English (US) | [▶ play](voices/am_eric.mp3) |
| `am_fenrir` | English (US) | [▶ play](voices/am_fenrir.mp3) |
| `am_liam` | English (US) | [▶ play](voices/am_liam.mp3) |
| `am_onyx` | English (US) | [▶ play](voices/am_onyx.mp3) |
| `am_puck` | English (US) | [▶ play](voices/am_puck.mp3) |
| `am_santa` | English (US) | [▶ play](voices/am_santa.mp3) |
| `bm_george` | English (UK) | [▶ play](voices/bm_george.mp3) |
| `bm_lewis` | English (UK) | [▶ play](voices/bm_lewis.mp3) |
| `bm_daniel` | English (UK) | [▶ play](voices/bm_daniel.mp3) |
| `bm_fable` | English (UK) | [▶ play](voices/bm_fable.mp3) |
| `em_alex` | Spanish | [▶ play](voices/em_alex.mp3) |
| `em_santa` | Spanish | [▶ play](voices/em_santa.mp3) |
| `hm_omega` | Hindi | [▶ play](voices/hm_omega.mp3) |
| `hm_psi` | Hindi | [▶ play](voices/hm_psi.mp3) |
| `im_nicola` | Italian | [▶ play](voices/im_nicola.mp3) |
| `pm_alex` | Portuguese (BR) | [▶ play](voices/pm_alex.mp3) |
| `pm_santa` | Portuguese (BR) | [▶ play](voices/pm_santa.mp3) |
| `jm_kumo` | Japanese | [▶ play](voices/jm_kumo.mp3) |
| `zm_yunjian` | Chinese | [▶ play](voices/zm_yunjian.mp3) |
| `zm_yunxi` | Chinese | [▶ play](voices/zm_yunxi.mp3) |
| `zm_yunxia` | Chinese | [▶ play](voices/zm_yunxia.mp3) |
| `zm_yunyang` | Chinese | [▶ play](voices/zm_yunyang.mp3) |
