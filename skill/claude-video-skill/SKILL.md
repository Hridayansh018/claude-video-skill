---
name: vdo-video
description: Turn a pasted video script into a finished narrated explainer video (MP4 + captions) in the stick-figure cartoon style, with Google Flow pictures, characters/objects that pop in on the matching narration line, an offline Kokoro voice, music and sound effects. Use whenever the user pastes a script and asks for a video, or asks to make, render or rebuild a vdo video.
---

# vdo-video: script to video

The engine lives in **VDO_HOME** = `{{VDO_HOME}}` (the folder holding `vdo.bat`, `vdo/`, `flow/`, `projects/`).
Every command below is `"{{VDO_HOME}}\vdo.bat" <command> ...`. On macOS/Linux use `"{{VDO_HOME}}/vdo.sh"`.
Pictures come from **Google Flow** (flow.google.com, Nano Banana image model) driven in a browser. Voice,
music, sound, motion, pop-ups, captions and the final render are done locally by the engine.

Run the work yourself, end to end; the user only pastes the script. Keep them posted in one line per stage.

## 0. Check the machine (once per session)

Run `vdo.bat doctor`. If it reports `[!!]`, stop and tell the user to double-click `setup.bat` in VDO_HOME
(see README.md there), then continue. If you cannot run commands on the user's computer at all, see
"Remote session" at the end.

## 1. Make the project

1. Pick a short name (letters, digits, `_`), e.g. `greece`.
2. Save the pasted script **exactly as given** to `{{VDO_HOME}}\projects\_inbox\<name>.md`.
3. `vdo.bat new "{{VDO_HOME}}\projects\_inbox\<name>.md" --name <name>`
   - options: `--scenes 1-5` (only some scenes), `--style oil` (oil-painting look), `--stickman 3,7` / `--oil 2`
     (per-scene style), `--image-duration 6` (seconds per picture, default 6), `--no-script-timing`
     (ignore timestamps in the script and follow the voice).
4. This creates `projects/<name>/project.json`, `images/`, `clips/`.

The parser understands scripts like:

```
#### Scene 3 (0:40 – 1:00)
* **Voiceover:** Then, around 1200 BC ...
* **Video Prompt:** A massive Mycenaean citadel ...
* **Popups:** king = a stern bearded king in a purple robe and gold crown @ king; crown = a golden crown (prop) @ gold
* **SFX:** fire, crowd
```

Plain paragraphs (no headings) become one scene each. If the script has no picture descriptions, the
voiceover is used; you will improve the prompts in step 3.

## 2. Add pop-ups (characters / objects over the background)

Open `project.json`. Wherever the narration introduces a person, animal or important object, make that
scene a pop-up scene (aim for roughly 1 scene in 3, at most 3 layers each). Either add a `**Popups:**` line to
the script before step 1, or edit the scene directly:

```json
"overlay": {
  "background": {"prompt": "the Athenian agora marketplace, stone colonnades, stalls, open square in the middle"},
  "background_motion": "push_in",
  "layers": [
    {"id": "socrates", "kind": "character", "height": 0.62,
     "image": {"prompt": "an old barefoot bearded philosopher in a white toga, one finger raised"},
     "popup": {"at": "Socrates", "x": 0.27, "y": 0.95, "from": "bottom"}},
    {"id": "scroll", "kind": "prop", "height": 0.2,
     "image": {"prompt": "a rolled parchment scroll tied with a red ribbon"},
     "popup": {"at": "wrote", "x": 0.76, "y": 0.42, "from": "scale"}}
  ]
}
```

- `at`: a word/phrase from that scene's voiceover (it appears just before the word is spoken) or seconds.
- `from`: `bottom` | `left` | `right` | `top` | `scale` (bounce in, best for props) | `fade`.
- `out`: optional word/seconds to leave again; default stays to the end of the scene.
- `x`, `y`: settle point (0–1). Characters: `y` is where the feet stand (0.9–0.97). Keep layers apart
  (x 0.25 / 0.5 / 0.75) and away from the caption area at the very bottom centre for props.
- `height`: fraction of frame height (characters 0.55–0.7, props 0.15–0.3).
- A whoosh and a pop are added automatically. Other layer keys: `"poses": [{"t": 3.0, "image": {...}}]`.

Other useful scene keys: `"continue": true` (keep the previous picture), `"image_count": 2`,
`"images": [{"prompt": "..."}]`, `"ambience": "crowd"`, `"sfx": ["thud"]`, `"clip": "clips/s04.mp4"` (a video
clip instead of pictures, see "Veo clips"). Sound names: `vdo.bat sfx-list`.

## 3. Plan and write the picture prompts

`vdo.bat plan "{{VDO_HOME}}\projects\<name>\project.json"`

This voices the script (Kokoro, offline), decides how many pictures each scene needs (from the voice length
and the image duration), resolves pop-up timings, and writes:
- `image_jobs.json`: one job per picture: `id`, `kind` (scene | background | character | prop | video),
  `file`, `narration`, `prompt`.
- `image_prompts.md`: the same, readable.

Now **improve every `prompt` in image_jobs.json** (edit the JSON; your edits are kept on re-plan):
- Keep the style text at the start and the "16:9 / no text" ending exactly as written.
- Scene pictures: show the stick figures *acting out what the narration says at that moment*. When a scene
  has several pictures, make each a different moment or shot (wide, medium, close-up).
- `background`: the place only, empty, with open space where the characters will stand.
- `character` / `prop`: one subject, full body, on plain white. Describe recurring characters the same way
  every time (same clothes, colours, beard, props) so they stay consistent across the video.
- No readable text, signs or captions in any prompt.

## 4. Make the pictures in Google Flow

Use the browser the session provides (the built-in browser, or Claude in Chrome); load its skill first if one
is listed. The user must be signed in to Google; if Flow shows a sign-in page, ask them to sign in.

1. Open `https://flow.google.com`, start a **New project**. In the settings chip next to the prompt box choose
   **Image**, model **Nano Banana** (latest), aspect **16:9**, outputs **x2**. (Images showed 0 credits
   when this skill was written; if Flow says a prompt costs credits, tell the user before continuing.)
2. Read `{{VDO_HOME}}\flow\flow_helper.js` and run its whole text with the browser's JavaScript tool. It
   returns `vdo helper ready` and adds `window.vdo`. Run it again after any page reload.
3. Work in batches of up to 5 jobs that are not done yet (`vdo.bat status <project.json>` lists them):
   1. JS: `await vdo.snapshot()`
   2. For each job in the batch, in order: click the prompt box ("What do you want to create?"), type the
      job's prompt, press Enter, wait 2 s.
   3. JS: `await vdo.waitIdle(); await vdo.fresh(); vdo.assign(["s01_1","s01_2", ...the batch ids in the order you submitted], 2)`
   4. `ok: true` gives `map` (job id → picture) and `alts` (both pictures of each prompt). `ok: false` means
      a prompt failed or was refused: rephrase it (often a word like a weapon or a name) and redo that batch
      one prompt at a time.
   5. Look at the results (screenshot of the gallery). If the first picture of a job has text, extra people
      in a `background`, a cut-off or scenery-filled `character`, or the wrong style, use the other one from
      `alts`, or regenerate that job.
4. Bring the batch into the project:
   - **Browser on the same computer as VDO_HOME (normal case):** the first time, ask the user if you may
     download the pictures to their Downloads folder. Then JS `await vdo.save(MAP, "<name>")` (MAP = the
     map from step 3.4 with any swaps), then `vdo.bat import "<project.json>"`. If Chrome asks to allow
     multiple downloads, ask the user to click Allow. Files are named `vdo__<name>__<job id>.jpg` and are
     moved into `images/`.
   - **Otherwise:** JS `await vdo.pack(MAP)` returns `{chunks: N}`; then for i = 0..N-1 run JS `vdo.chunk(i)`
     (each result is saved as a tool-result file because it is large); then
     `vdo.bat import "<project.json>" --chunks <all those files>`.
5. Repeat until `vdo.bat status` says everything is ready. Then `vdo.bat sheet "<project.json>"` and look at
   `contact_sheet.jpg` once to check the whole set.

## 5. Build

`vdo.bat build "{{VDO_HOME}}\projects\<name>\project.json"`

- Add `--preview` for a quick half-size check first on long videos. `--allow-missing` builds with
  placeholders when some pictures are not made yet.
- Takes about 2–4 minutes per minute of video. Output: `projects/<name>/output/<name>.mp4` (1080p, 30 fps,
  AAC 48 kHz, −14 LUFS) and `<name>.srt` captions; `report.json` lists warnings.
- Check two or three frames (e.g. extract with ffmpeg at a pop-up moment) before telling the user it is done.
- Tell the user where the MP4 is. Rebuilding after a change only re-renders what changed.

## Changing things afterwards

- Different picture: replace `images/<id>.jpg` (or regenerate in Flow), then build.
- Different voice: in project.json `"voice": {"voice": "bm_george"}`; other Kokoro voices: `bm_lewis`,
  `bf_emma`, `am_michael`, `af_heart`, ...; `"speed": 0.95`.
- Music: `"audio": {"music": "auto", "music_mood": "warm" | "wonder" | "serious", "music_gain_db": -21}`,
  or a file path, or `null` for none.
- Captions burned into the picture: `"subtitles": {"burn_in": true}`.
- Timing: `image_duration` (project or scene), scene `duration`.

## Veo clips (optional, costs Flow credits)

For a scene that really needs movement, generate a video in Flow's **Video** mode (8 s clips), download it
(ask the user first), save it as `projects/<name>/clips/<scene id>.mp4` and set the scene's
`"clip": "clips/<scene id>.mp4"`. The engine fits the clip to the scene (slows or loops it), mixes its own
sound under the narration (`"clip_volume_db": -14`, `"clip_audio": false` to mute). Veo videos carry a
visible watermark unless the user's plan removes it; `"clip_crop": 0.05` zooms in slightly to hide a corner
mark. Mention credits and the watermark to the user before using clips.

## Remote session (you cannot run commands on the user's computer)

If the only shell you have is a cloud workspace: copy VDO_HOME's `vdo/`, `flow/`, `requirements.txt`,
the project folder and `models/` into the workspace (the folder bridge / staging tools), `pip install -r
requirements.txt`, run the same commands with `python -m vdo ...` from the copied folder, use the
`vdo.pack` / `vdo.chunk` route for pictures, then send the MP4 to the user and write it back into
`projects/<name>/output/` on their computer.

## Troubleshooting

- `doctor` says Kokoro model missing → `setup.bat` again (it downloads `models/kokoro-v1.0.onnx` and
  `models/voices-v1.0.bin`).
- Video will not play on Windows (0xC00D36C4) → rebuild; the engine always writes 48 kHz AAC.
- A pop-up has a white box around it → the character picture did not have a plain white background;
  regenerate it with "isolated on a plain pure white background".
- Flow page layout changed and the helper finds no pictures → screenshot the page, find the gallery images
  and adapt: pictures are `<img>` elements whose `src` contains `flow-content.google/image/`.
