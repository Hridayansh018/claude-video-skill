---
name: claude-video-skill
description: Turn a pasted video script into a finished narrated explainer video (MP4 + captions) in a stick-figure cartoon style, with Google Flow pictures, recurring characters that walk, talk and gesture over backgrounds, an offline Kokoro voice, music and a library of sound effects. Use whenever the user pastes a script and asks for a video, or asks to make, render or rebuild a vdo video.
---

# claude-video-skill: script to video

The engine lives in **VDO_HOME** = `{{VDO_HOME}}` (the folder holding `vdo.bat`, `vdo/`, `flow/`). Videos are saved in
the user's **main folder**, chosen during setup: run `vdo.bat where` to see it (`main:` and `projects:` lines). Below,
`<main>` means that folder and `<folder>` means `<main>\projects\<slug>`, the folder of one video.
Every command below is `"{{VDO_HOME}}\vdo.bat" <command> ...`. On macOS/Linux use `"{{VDO_HOME}}/vdo.sh"`.
Pictures come from **Google Flow** (flow.google.com, Nano Banana image model) driven in a browser. Voice,
music, sound, motion, characters, captions and the final render are done locally by the engine.

Run the work yourself, end to end; the user only pastes the script. Keep them posted in one line per stage.

**Rules that never change**
- Pictures only, no AI video clips (no Veo). Characters and objects are made as pictures on a flat green
  screen, cut out by the engine, and animated by the engine.
- The engine crops the Flow corner mark automatically (`corner_crop`, default 0.08). Do not turn it off.
- Never put readable text, signs or captions into a picture prompt.
- Never delete the user's files without asking. Replaced or unmatched pictures are moved to `images_unused\`, not removed.
- Never create `.bat` / `.sh` files in the engine folder or `<main>`. Each project already has its own launchers
  (`build.bat`, `mp4.bat`, `preview.bat`, `status.bat`, `files.bat`, `open_output.bat`) inside `<folder>`;
  `vdo.bat launchers <project.json>` rewrites them. Do not make others.
- Use the built-in browser, not Chrome, for all web work, unless the user says otherwise.

## Where everything is saved

```
<main>\projects\<slug>\                     <folder>
    script.md  project.json  image_jobs.json  image_prompts.md  contact_sheet.jpg
    build.bat mp4.bat preview.bat status.bat files.bat open_output.bat  (+ .sh)   launchers for this video
    images\            every picture, as .jpg
    images_unused\     pictures that match no job, or were replaced
    output\            <slug>.mp4  <slug>.srt  <slug>_mix.m4a (final mix)  chapters.txt  package.md  capcut_draft\
    output\work\       voice\ (one .wav per scene + a .json with its word timings), music_*.wav, stems\, plan.json
```

- Pictures: **never download to the desktop or Downloads.** Bring them in with the in-page pack (`vdo.pack` then
  `vdo.chunk`) and `vdo.bat import <project.json> --chunks ...`; the import writes them straight into `<folder>\images\`
  as `.jpg`, named by job id: `s05c_1.jpg` (scene picture), `s12a_bg.jpg` (background), `cast_<name>.jpg` (character
  master), `cast_<name>_walk1.jpg` (pose), `prop_<name>.jpg`. Use the names in `image_jobs.json` (`file`); do not invent new ones.
  Import also moves anything that matches no job to `images_unused\` (`vdo.bat tidy <project.json>` does just that).
- Narration, music and sound effects are saved by the build in `output\work\` as above. The final mix, MP4 and SRT go in `output\`.
- When a job is done, run `vdo.bat files <project.json>` and give the user the list it prints: what was saved, where, with counts.

## Pictures only (when the user asks for just the pictures, or says "stop after the pictures")

Do steps 1-4 of Autopilot and then STOP; do not build or push to CapCut. Reuse the same rules:
- Built-in browser, the user's signed-in Google account. Check once: Image, Nano Banana, x1, 16:9.
- Submit ALL prompts first, up to 8 per batch; wait until idle before bringing a batch in. Match pictures to jobs by
  submission order (the gallery lists newest first). If a batch comes back short, find the missing one on a contact
  sheet and redo only that prompt. Use the page helper; never scroll screen by screen; never click a gallery tile.
- When the export size is 2k, use Flow's 2K upscale for every background and scene picture if Flow offers it (tell the
  user once if it does not).
- Make: for every scene a wide and a medium shot, plus backgrounds and props as needed (pop-up scenes get a background
  and their wide / medium shots). Cast: as many characters as the story needs, each with a master picture and ALL 8
  poses (talk, think, point, shock, angry, sad, walk1, walk2). One character per prompt, on a flat green screen (magenta if
  the character is green), full body, nothing cropped. Make each pose with the master attached and check face and
  clothes match it. No readable text in any picture.
- Look at the contact sheet once. Redo only pictures with text, merged figures, cut-off bodies, scenery behind a
  green-screen character, or the wrong style.
- Then report: counts by type (from `vdo.bat files`), the contact sheet, and anything redone or still missing.

## Autopilot: give a link, topic or script, get the finished video

When the user gives a source (video link, topic or script) with a title, name or length, run the WHOLE job without
stopping to ask or report: research and script, project, pictures, build, package, delivery. Do not pause after
the pictures or between batches, and do not ask "shall I continue". Stop only when (a) blocked (Google sign-in
needed, Flow refuses repeatedly, a tool is disconnected) or (b) the user says "stop". Progress is one line per
stage and never waits for a reply. Use sensible defaults for anything not given: voice `bm_george` (calm British
male), `"resolution": "2k"`, captions `yellow_pop` burned in, story type `auto`, project name from the title.
Save everything as described in "Where everything is saved".

1. **Source.** Link: read its title, description and transcript or content, keep the topic and facts, and rewrite the
   script in your own words (never copy). Topic: research it (current, citable sources). Script: use it as given.
2. **Script** (about 140 spoken words per minute of length), in the engine's scene format: `**Story Type:**`, `## Cast`,
   numbered scenes with Voiceover, Video Prompt, `**Mood:**`, `**Popups:**`, `**SFX:**`. A hook inside the first 30 s,
   a new open loop every 60-90 s, calm British narrator, no like/subscribe asks, no hype words ("insane", "mind-blowing",
   "you won't believe"), uncertain facts hedged ("records say", "historians suspect").
3. **Project and plan:** `new`, then `plan`; improve the prompts in image_jobs.json (a wide and a medium shot per scene,
   backgrounds and props as needed, one character per cast prompt, never readable text).
4. **Pictures in Flow** (built-in browser, signed-in account, Image / Nano Banana / x1 / 16:9): submit in batches of 8,
   wait idle, `assign` by submission order (the gallery lists newest first), bring them in with `pack` and `chunk` and
   `import` (no downloads to the desktop; do not scroll by hand, the helper scans the gallery). Masters first, then poses
   (talk, think, point, shock, angry, sad, walk1, walk2) with the master attached, then props. If a batch comes back
   short, find the missing prompt on a contact sheet and redo only that one. Look at `contact_sheet.jpg` once and redo
   only pictures with merged figures, text or the wrong style. Then straight on to the build.
5. **Push to CapCut** at the chosen size and captions (`build <project.json> --res 2k --captions yellow_pop`). By default
   `build` does NOT render an MP4 on this PC: it makes the voice, music and effects, then sends the whole project to
   CapCut as an editable draft (see "Push to CapCut"). Add `--mp4` only if the user also wants an MP4 rendered here.
   Check the draft's folder and report; fix anything wrong and push once more.
6. **Package** into `<folder>\output\package.md`: 5 titles (45-65 characters, each with the real minute count),
   a thumbnail idea (one subject, big contrast, at most 4 words of text), and a description with chapters from
   `vdo.bat chapters <project.json>` (rename the lines if needed), sources, and any SOUND_CREDITS.txt lines.
7. **Deliver:** tell the user the project is in CapCut (Drafts) and give them the SRT and package.md (the MP4 too if `--mp4`).
   They are already in `<folder>\output\` (write a copy to any other save location the user named). Run `vdo.bat files <project.json>` and finish with its list (what was saved, where, counts)
   plus anything that failed or was changed.

## 0. Check the machine (once per session)

Run `vdo.bat doctor`. If it reports `[!!]`, stop and tell the user to double-click `setup.bat` in VDO_HOME
(README.md there), then continue. If you cannot run commands on the user's computer, see "Remote session".
Then run `vdo.bat where`. If `main:` is just the engine folder and the user has not chosen one, ask once: "Where should I
save your videos? (a main folder; each video gets its own folder inside it)", then run `vdo.bat init --main "<their folder>"`.

## 1. Make the project

1. Pick a short name (letters, digits, `_`), e.g. `greece`.
2. Save the pasted script **exactly as given** to `<main>\projects\_inbox\<name>.md`.
3. `vdo.bat new "<main>\projects\_inbox\<name>.md" --name <name>` (the project is created in `<main>\projects\<name>`
   and gets its own launchers there; `--projects-dir` overrides the place for one project).
   - options: `--scenes 1-5`, `--style oil`, `--stickman 3,7` / `--oil 2` (per-scene style),
     `--image-duration 6`, `--no-script-timing` (ignore timestamps, follow the voice).
4. This creates `<folder>\project.json`, `images\`, `images_unused\` and the launchers. Use `<folder>\project.json` in the commands below.

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

`vdo.bat plan "<folder>\project.json"`

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

## 5. Build = push to CapCut

`vdo.bat build "<folder>\project.json"`

- **The default is CapCut, not a local render.** The build makes voice, music, effects and captions, then writes an
  editable draft to `<folder>\output\capcut_draft\<name>` and copies it into CapCut. The user finishes and exports in CapCut.
- `--mp4` also renders the MP4 here (1080p, 2K with `--res 2k`; 30 fps, AAC 48 kHz, -14 LUFS, plus `<name>_mix.m4a`);
  `--mp4-only` renders just the MP4 and does not touch CapCut. `--preview` is a quick half-size run; `--allow-missing` uses placeholders.
- `<name>.srt` is always written; `report.json` lists warnings.
- Only when an MP4 was rendered: check two or three frames (a pop-up moment, a walking moment) for a green fringe,
  a wrong pose or the corner mark.

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

## Push to CapCut

If the user wants to edit in CapCut ("send it to CapCut", "make it a CapCut draft", "I want to tweak it in CapCut"):
`vdo.bat build "<project.json>"` (add `--res 2k --captions yellow_pop`) does this by default; `vdo.bat capcut` is the same
without the rest. Add `--mp4` to also get the MP4. It writes the draft to `<folder>\output\capcut_draft\<name>` and,
when CapCut is installed, copies it into CapCut's project folder. CapCut must be closed: if the command says it is open, ask
the user to close it (or, with their OK, pass `--close-capcut`; unsaved work in CapCut is lost) and run it again. Tell the
user to open CapCut and find the project under Drafts, and what is inside: one clip per cut with transitions, separate
voice / effects / ambience / music tracks, and an editable caption track. In Autopilot, this is the final step; do not render an MP4
unless the user asks for one.

## Turning the user's words into settings

When the request mentions a feature, set it in project.json (or pass the build flag) before building:
- "2K", "1440p", "high quality" -> `"resolution": "2k"` / `--res 2k` (say it takes about twice as long). "4K" -> `4k`.
- "captions", "subtitles burned in", "yellow captions" -> `"subtitles": {"burn_in": true, "style": "yellow_pop"}`; "white
  captions", "outlined" -> `white_outline`. No mention of captions: leave burn-in off (the `.srt` is always written).
- A voice by name or feel -> `"voice": {"voice": ...}` (offer 3 from the README list if they gave only a feel).
- A mood or genre -> `"story_type"`; louder/quieter music -> `music_gain_db`; no effects -> `auto_events` and `auto_ambience` false.
- "Give me the MP4", "render it here" -> add `--mp4` (or `--mp4-only` to skip CapCut). Otherwise everything goes to CapCut.
- A character who walks in, talks or points -> `## Cast` plus `**Popups:**` lines.

## First-time check ("set up claude-video-skill")

If the user asks you to set the skill up: run `vdo.bat doctor` (fix `[!!]` with setup.bat), confirm the skill is listed,
open Flow and check the settings chip (Image, Nano Banana, x1, 16:9; ask them to sign in if needed), then make a
10-second two-scene test project with `--res 1080p --captions yellow_pop`, push it to CapCut and report where the draft is and anything that failed.

## Changing things afterwards

- Different picture: replace `images/<id>.jpg` (or regenerate in Flow), then build.
- Voice: `"voice": {"voice": "bm_george", "speed": 0.95}`. 50 voices (25 female, 25 male) with samples in `voices/` (`voices/index.html` plays them; names and languages in README.md). The language follows the voice. If the user asks for a voice by feel ("deep", "young woman"), offer 3 names from the README and let them listen.
- Music: follows the story type. `"story_type": "auto"` (default) reads the script and picks war, tense, dark, sad, triumph, mystery, adventure, epic, wonder, warm or calm; each scene can switch style when it clearly says so (a victory scene in a war story gets triumph). Force it with `"story_type": "war"` (script line `**Story Type:** war`), or per scene `"mood": "tense"` (`**Mood:** tense`). `"audio": {"music_mood": "epic"}` fixes one style for the whole video. Aliases: cinematic = epic, thriller = tense, horror = dark, battle = war, history = epic. `music` can also be a file path or `null`.
- Captions burned in: `"subtitles": {"burn_in": true, "style": "yellow_pop"}`. Styles: `scene` (per-scene look, default), `white_outline` (white capitals, thick black outline), `yellow_pop` (yellow capitals, black outline and shadow, quick pop-in). Or at build time: `vdo.bat build <project.json> --captions yellow_pop` (this also turns burn-in on). The `.srt` is always written.
- Export size: `"resolution": "2k"` (2560x1440; also 720p, 1080p, 4k) or `vdo.bat build <project.json> --res 2k`. 2K builds use a lower CRF (cleaner) and take about twice as long. Pictures are scaled up with Lanczos, so give Flow's 2K upscale for backgrounds and scene pictures when it is offered. Crop amount: `"corner_crop": 0.08`.
- Timing: `image_duration` (project or scene), scene `duration`.

## Remote session (you cannot run commands on the user's computer)

Copy VDO_HOME's `vdo/`, `flow/`, `requirements.txt`, the project folder and `models/` into the workspace,
`pip install -r requirements.txt`, run `python -m vdo <command>` there, use `vdo.pack` / `vdo.chunk` for pictures,
then write the results back into `<folder>\output\` on the user's computer. CapCut cannot be reached from a remote workspace, so
there render the MP4 (`--mp4-only`) and send it, and tell the user to run `capcut.bat`/`build.bat` on their PC to push the draft.

## Troubleshooting

- Kokoro model missing → run `setup.bat` again.
- Video will not play on Windows (0xC00D36C4) → rebuild; the engine always writes 48 kHz AAC.
- Green edge or holes around a character → the screen was not flat; regenerate the picture with the screen text
  from the prompt, or make the subject magenta-screened (`"key": "magenta"` on the cast member).
- Two characters in one picture → regenerate each one with its own prompt.
- Flow's layout changed and the helper finds no pictures → screenshot the page and adapt the helper: pictures are
  `<img>` elements whose `src` contains `flow-content.google/image/`.
