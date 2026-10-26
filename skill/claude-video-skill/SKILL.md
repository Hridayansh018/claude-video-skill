---
name: claude-video-skill
description: Turn a pasted video script into a finished narrated explainer video (MP4 + captions) in a stick-figure cartoon style, with Google Flow pictures, recurring characters that walk, talk and gesture over backgrounds, an offline Kokoro voice, music and a library of sound effects. Use whenever the user pastes a script and asks for a video, or asks to make, render or rebuild a vdo video.
---

# claude-video-skill: script to video

The engine lives in **VDO_HOME** = `{{VDO_HOME}}` (the folder holding `vdo.bat`, `vdo/`, `flow/`, `projects/`).
Every command below is `"{{VDO_HOME}}\vdo.bat" <command> ...`. On macOS/Linux use `"{{VDO_HOME}}/vdo.sh"`.
Pictures come from **Google Flow** (flow.google.com, Nano Banana image model) driven in a browser. Voice,
music, sound, motion, characters, captions and the final render are done locally by the engine.

Run the work yourself, end to end; the user only pastes the script. Keep them posted in one line per stage.

**Rules that never change**
- Pictures only, no AI video clips (no Veo). Characters and objects are made as pictures on a flat green
  screen, cut out by the engine, and animated by the engine.
- The engine crops the Flow corner mark automatically (`corner_crop`, default 0.08). Do not turn it off.
- Never put readable text, signs or captions into a picture prompt.

## 0. Check the machine (once per session)

Run `vdo.bat doctor`. If it reports `[!!]`, stop and tell the user to double-click `setup.bat` in VDO_HOME
(README.md there), then continue. If you cannot run commands on the user's computer, see "Remote session".

## 1. Make the project

1. Pick a short name (letters, digits, `_`), e.g. `greece`.
2. Save the pasted script **exactly as given** to `{{VDO_HOME}}\projects\_inbox\<name>.md`.
3. `vdo.bat new "{{VDO_HOME}}\projects\_inbox\<name>.md" --name <name>`
   - options: `--scenes 1-5`, `--style oil`, `--stickman 3,7` / `--oil 2` (per-scene style),
     `--image-duration 6`, `--no-script-timing` (ignore timestamps, follow the voice).
4. This creates `projects/<name>/project.json`, `images/`.

Script format the parser understands (everything except the voiceover is optional):

```
## Cast
* socrates: an old bald stick figure philosopher with a big white beard, white toga, barefoot
* student: a young stick figure student in a blue tunic holding a wax tablet

#### Scene 3 (0:40 – 1:00)
* **Voiceover:** Then, around 1200 BC ...
* **Video Prompt:** A massive Mycenaean citadel ...
* **Popups:** socrates @ Socrates | walks in from left | talks | points @ question; scroll = a rolled scroll (prop) @ wrote
* **SFX:** crowd, fire
```

Plain paragraphs (no headings) become one scene each.

## 2. Cast and pop-ups (characters and objects over a background)

**Cast** = recurring characters. Describe each once (same clothes, colours, beard, props); the engine makes
one master picture and then every pose from it, so the character looks identical in every scene.
Add a `## Cast` section to the script, or `"cast": {"socrates": {"look": "..."}}` in project.json.

Make roughly 1 scene in 3 a pop-up scene (at most 3 layers). Popup line syntax:
`name @ cue | action | action; other = description (prop) @ cue`

- `@ cue` is a word or phrase from that scene's voiceover; it appears just before the word is spoken.
- Actions: `walks in from left|right`, `runs in from ...`, `walks to centre|left|right|0.4 @ word`,
  `leaves|walks off|runs off [left|right] @ word`, `talks [@ word]` (mouth moves while the voice speaks),
  `points|cheers|waves|thinks|shocked|sad|angry|fights|bows|sits|kneels|falls @ word`, `stands left|centre|right`.
- `(prop)` marks an object (drops in with a bounce). Props are one picture; characters use poses.
- Poses the engine can ask for: base, walk1, walk2, run1, run2, talk, point, cheer, wave, think, shock, sad,
  angry, fight, bow, sit, kneel, fall. Only the poses a scene uses are made.
- JSON equivalent per layer: `{"id","cast","kind","height","popup":{"at","x","y","from","out","out_to"},
  "walk":[{"to","at","run"}],"talk":true,"gestures":[{"pose","at"}]}`; `from` is bottom | left | right | top |
  scale | fade | walk_left | walk_right | run_left | run_right.

## 3. Plan and write the picture prompts

`vdo.bat plan "{{VDO_HOME}}\projects\<name>\project.json"`

Voices the script (Kokoro), decides how many pictures each scene needs, resolves pop-up timing, and writes
`image_jobs.json` (one job per picture: `id`, `kind` scene | background | cast | cast_pose | prop, `file`,
`narration`, `prompt`, and `reference` for poses) and `image_prompts.md`.

Improve every `prompt` in image_jobs.json (your edits survive re-planning):
- Keep the style text at the start and the "16:9 / no text" ending.
- Scene pictures: stick figures acting out what the narration says at that moment; different shot per picture.
- `background`: the place only, empty, with open space where the characters will stand.
- `cast` (master): one character, full body, on a flat green screen (`#00B140`). The engine writes this
  already; if the character is green (leaves, frog), the job uses magenta instead. Keep it.
- `cast_pose`: starts "Use the attached reference image..." and must be made with the master attached.
- `prop`: one object on the same flat screen colour.

## 4. Make the pictures in Google Flow

Use the browser the session provides (built-in browser or Claude in Chrome); load its skill first. The user
must be signed in to Google; if Flow shows a sign-in page, ask them to sign in.

1. Open `https://flow.google.com`, start a **New project**. In the settings chip choose **Image**, model
   **Nano Banana** (latest), aspect **16:9**, outputs **x1** (or x2 to choose the better one).
2. Read `{{VDO_HOME}}\flow\flow_helper.js` and run its whole text with the browser's JavaScript tool. It adds
   `window.vdo`. Run it again after any page reload.
3. Order of work: **backgrounds and scene pictures**, then **cast masters**, then **cast poses**, then props.
   Batches of up to 5 jobs not yet done (`vdo.bat status <project.json>` lists them):
   1. JS `await vdo.snapshot()`
   2. For each job: click the prompt box, type the prompt, press Enter, wait 2 s.
      - **Cast masters: one prompt per character, never two characters in one prompt** (Flow merges them
        into one picture). Check the green is flat and the whole body is visible.
      - **Cast poses and anything with a `reference`:** first attach the character's master picture to the
        prompt box (the "+" / "Add ingredients to the prompt box" picker lists the project's pictures; type part of the
        master's title into the picker's search box and click the single result, so the right picture is chosen
        every time; check the chip shows the green picture before sending), then type the pose prompt. Check that face and clothes match the master.
   3. JS `await vdo.waitIdle(); await vdo.fresh(); vdo.assign([ids in submission order], 1)` (use 2 for x2)
   4. `ok: false` means a prompt failed or was refused: rephrase (often a weapon word or a real name) and redo
      that one prompt alone. Look at the results; redo pictures with text, merged figures, cut-off bodies,
      scenery behind a green-screen subject, or the wrong style.
4. Bring the batch in:
   - Browser on the same computer as VDO_HOME: ask the user once if you may download pictures to Downloads,
     then JS `await vdo.save(MAP, "<name>")` and `vdo.bat import "<project.json>"`. If Chrome asks to allow
     multiple downloads, ask the user to click Allow.
   - Otherwise: JS `await vdo.pack(MAP)` gives `{chunks: N}`; run `vdo.chunk(i)` for each i, then
     `vdo.bat import "<project.json>" --chunks <those files>`.
5. Repeat until `vdo.bat status` says everything is ready; `vdo.bat sheet "<project.json>"` and look at
   `contact_sheet.jpg` once.

Picture size: Flow gives 1376x768. The crop trims about 8%, then the engine scales back up with Lanczos, which is
fine for pans and zooms. If Flow offers a 2K download or upscale for a picture, use it for backgrounds and scene
pictures (the sharper the source, the less the crop costs); do not go to 4K, it is slow and not needed.

Flow's page changed in late 2026: next to the prompt box there is also an agent chat panel. Ignore it; use the prompt box at the bottom of the gallery (settings chip: Nano Banana, x1, 16:9). Never click a gallery tile, it opens an edit view (go back with the browser's Back). Pictures are now `<img>` elements from `flow.google.com/asb/...`; the helper handles both addresses.

Flow marks its pictures with a small sparkle in the bottom-right corner. The engine crops that corner out
(`corner_crop`) and cut-out characters discard their surroundings, so no extra step is needed. Tell the user
once that Google's invisible SynthID mark is still inside the pictures; it cannot be removed and does not show.

## 5. Build

`vdo.bat build "{{VDO_HOME}}\projects\<name>\project.json"`

- `--preview` for a quick half-size check; `--allow-missing` builds with placeholders.
- About 2–4 minutes per minute of video. Output: `projects/<name>/output/<name>.mp4` (1080p, 30 fps, AAC 48 kHz,
  -14 LUFS) and `<name>.srt`; `report.json` lists warnings.
- Check two or three frames (ffmpeg at a pop-up moment, at a walking moment) before saying it is done; look for
  a green fringe around characters, a wrong pose, or the corner mark.
- Tell the user where the MP4 is.

## Sound

- Narration-driven: the engine listens to the script, so "the crowd cheered" plays a cheer under that word,
  "explosion" a blast, and so on. A quiet ambience bed is chosen from what a scene describes.
- Sources: real recorded sounds from SFXMint (CC0, free, no key; a starter pack is bundled in
  `sfx_library/_sfxmint/`, `vdo.bat sfx-fetch` downloads any missing ones) for blast, thunder, sword clash,
  cheer, applause, fanfare, drums, gallop, fire, wind, rain, sea and similar. Anything else is generated in code.
  `vdo.bat sfx-list` shows which is which. Your own files in `sfx_library/<name>/` override both.
  `"audio": {"sfx_source": "builtin"}` uses only the generated sounds.
- Sounds are sparse on purpose: only a few well-matched effects, and background beds only for places and
  weather (fire, wind, rain, sea, cave, countryside, night). No talking-crowd beds unless asked for.
- Per scene: `"sfx": ["blast"]`, `"ambience": "fire"`, `"auto_sfx": false`. In the script: `**SFX:** fire, wind`
  or `@ word` to time one: `**SFX:** blast @ exploded`.
- Transitions use a soft, quiet sound (`"audio": {"transition_sfx": "auto" | "none" | "<name>", "transition_gain_db": 0}`).
  Pop-ups use a soft pop. If a user finds one too loud, lower `sfx_gain_db` / `transition_gain_db`; remove
  transition sounds only if that is not enough.
- Music stays at one steady level for the whole video (it only dips under the voice); effects never change it, and the final loudness step uses a fixed gain.
- Levels live under `"audio"`: `music_gain_db` (default -15), `duck_db` (-8), `sfx_gain_db` (-6),
  `ambience_gain_db` (-21), `event_gain_db` (0), `auto_events`, `auto_ambience`, `max_events_per_scene`.

## Changing things afterwards

- Different picture: replace `images/<id>.jpg` (or regenerate in Flow), then build.
- Voice: `"voice": {"voice": "bm_george", "speed": 0.95}`. 50 voices (25 female, 25 male) with samples in `voices/` (`voices/index.html` plays them; names and languages in README.md). The language follows the voice. If the user asks for a voice by feel ("deep", "young woman"), offer 3 names from the README and let them listen.
- Music: follows the story type. `"story_type": "auto"` (default) reads the script and picks war, tense, dark, sad, triumph, mystery, adventure, epic, wonder, warm or calm; each scene can switch style when it clearly says so (a victory scene in a war story gets triumph). Force it with `"story_type": "war"` (script line `**Story Type:** war`), or per scene `"mood": "tense"` (`**Mood:** tense`). `"audio": {"music_mood": "epic"}` fixes one style for the whole video. Aliases: cinematic = epic, thriller = tense, horror = dark, battle = war, history = epic. `music` can also be a file path or `null`.
- Captions burned in: `"subtitles": {"burn_in": true}`. Crop amount: `"corner_crop": 0.08`.
- Timing: `image_duration` (project or scene), scene `duration`.

## Remote session (you cannot run commands on the user's computer)

Copy VDO_HOME's `vdo/`, `flow/`, `requirements.txt`, the project folder and `models/` into the workspace,
`pip install -r requirements.txt`, run `python -m vdo <command>` there, use `vdo.pack` / `vdo.chunk` for pictures,
then send the MP4 and write it back into `projects/<name>/output/` on the user's computer.

## Troubleshooting

- Kokoro model missing → run `setup.bat` again.
- Video will not play on Windows (0xC00D36C4) → rebuild; the engine always writes 48 kHz AAC.
- Green edge or holes around a character → the screen was not flat; regenerate the picture with the screen text
  from the prompt, or make the subject magenta-screened (`"key": "magenta"` on the cast member).
- Two characters in one picture → regenerate each one with its own prompt.
- Flow's layout changed and the helper finds no pictures → screenshot the page and adapt the helper: pictures are
  `<img>` elements whose `src` contains `flow-content.google/image/`.
