# Pitch video pipeline

Renders the Tideway demo/pitch video (at most 4:55) from `storyboard.json` in one command.
Narration is synthesised, the live app is recorded in headless Chrome, and ffmpeg composes
the final MP4. Everything runs locally against a fresh synthetic database.

## Re-render (one command)

```powershell
C:\Users\Administrator\tideway-tools-venv\Scripts\python.exe scripts\pitch_video\build.py
```

Outputs (all under the git-ignored `dist/video/`):

| File | What it is |
|---|---|
| `tideway-pitch.mp4` | H.264 High + AAC, 1920x1080, 30 fps, yuv420p, `+faststart`, burned-in captions |
| `tideway-pitch.srt` | Sidecar captions with the same timing |
| `build-log.json` | Scene start times and lengths, skipped scenes, voice, TTS engine, ffmpeg/Node/Chrome versions, source commit, SHA-256 |
| `stills/still-{10,35,60,85}.jpg` | Review frames at 10/35/60/85% of the video |
| `app.log`, `work/` | App log, cached narration audio, slide HTML and failure screenshots (`work/debug/`) |

`build.py` does the following:

1. Synthesises narration for every enabled scene (`narrate.py`). Audio is cached by voice, rate and text, so only changed lines are re-synthesised.
2. Deletes `data/video.sqlite3` and starts `python run.py --port 8792 --db data/video.sqlite3`. `data/` is git-ignored.
3. Runs `record.mjs` to record each scene.
4. Stops the app.
5. Composes the video with 0.5 s crossfades, a loudness-normalised narration track and captions.

The build fails loudly if the video would run past `max_seconds` (295 s). It also stops if the recorder fails or if there is less than 400 MB of free disk space before recording or composition.

Options:

- `--keep-clips` keeps the per-scene clips.
- `--reuse-recording` recomposes from kept clips without re-recording.
- `--no-burn-subtitles` writes only the `.srt` captions.
- `--voice en-GB-RyanNeural` switches the voice.

### One-time tool setup

The tools venv lives outside the repo:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m venv C:\Users\Administrator\tideway-tools-venv
C:\Users\Administrator\tideway-tools-venv\Scripts\python.exe -m pip install --no-cache-dir imageio-ffmpeg edge-tts
```

You also need Node 22+ and Google Chrome. The app itself runs with the system Python 3.11 (override with `TIDEWAY_PYTHON`).

- **Voice:** edge-tts needs network access. If it fails, `narrate.py` falls back to Windows SAPI (System.Speech), and `build-log.json` records which engine was used.
- **ffmpeg:** `imageio_ffmpeg.get_ffmpeg_exe()` is used, or the `FFMPEG` environment variable if set.

## How recording works

- **Viewport and frames:** the browser uses a 1280x720 CSS viewport at device scale 1.5, so every frame is a sharp 1920x1080 image with text that is 1.5 times larger and legible.
- **Capture:** `Page.startScreencast` frames are kept in memory, resampled to a constant 30 fps and piped straight into ffmpeg. No frame files touch the disk.
- **Scene length:** `lead + narration + tail + crossfade`, or longer if the recorded actions take more time. Audio and picture cannot drift apart.
- **Slides:** `slide.html` uses Tideway's own fonts (`web/fonts`) and colours (`web/styles.css`). Slide elements animate in once recording starts.

## Add or change a scene

Edit `storyboard.json`. Scenes play in order, and each one has an `id`, a `kind` and its `narration`. Keep narration true to README/docs: no invented statistics, and say "synthetic" where it applies.

**Slide scene:**

```json
{"id": "my-slide", "kind": "slide", "narration": "...",
 "slide": {"layout": "cards", "kicker": "Small caps line", "title": "Line one|Line two with *highlight*",
           "subtitle": "...", "items": [{"tag": "Tag", "h": "Heading", "p": "Text"}],
           "stats": [{"label": "...", "value": "...", "note": "..."}], "chips": ["..."], "people": ["..."], "footnote": "..."}}
```

Layouts are `hero`, `cards`, `stats` and `team`. Leave out any field you don't need.

**Live app scene:**

```json
{"id": "treasury", "kind": "app", "optional": true, "requires": "[data-view=treasury]",
 "setup": [{"do": "view", "name": "treasury"}],
 "narration": "...",
 "steps": [{"do": "click", "selector": "[data-action=treasury-tab][data-tab=health]", "at": 0.3}]}
```

- `setup` steps run before recording starts, so put navigation and resets there. `steps` are recorded.
- `"at": 0.3` holds a step until 30% of the scene's narration has played. This keeps the picture in sync with the words.
- `requires` is a CSS selector checked before setup. If it is missing and `"optional": true`, the scene is skipped and listed under `skipped_scenes` in `build-log.json`. Without `optional`, the build fails.
- `"enabled": false` disables a scene, as with the `own-ai-gpu` placeholder.

Available step operations (`do`):

| `do` | Fields | Effect |
|---|---|---|
| `navigate` | `url` (relative to the app), `ready` (JS) | Opens a page |
| `login` | `id`, `pin` | Signs in through the session API, then reloads |
| `reload` | | Reloads the page |
| `view` | `name` | Clicks the `[data-view=name]` nav item |
| `click` | `selector`, `highlight` (default true), `optional` | Shows a pink highlight ring, then clicks |
| `highlight` | `selector`, `ms` | Shows the highlight ring only |
| `hover` | `selector`, `click` | Moves the real mouse (CDP) to the element, so tooltips appear |
| `type` | `selector`, `text`, `cps` | Types visibly |
| `set` | `selector`, `value` | Sets a value instantly |
| `submit` | `selector` | Calls `requestSubmit()` on a form |
| `wait` | `for` (JS), `timeout` | Waits until the JS expression is truthy |
| `pause` | `ms` | Waits for a fixed time |
| `scroll` | `selector` with `block`/`offset`, or `by`, or `y` | Smooth scroll |
| `storage` | `key`, `value` | Sets a `localStorage` value, for example `tideway.help.v1 = off` |
| `eval` | `js` | Runs arbitrary page JS (an awaited promise is allowed) |

After editing, run `node scripts/pitch_video/format_storyboard.mjs` to keep one step per line.

For a quick preview of a few scenes against an app you started yourself, pass the scene ids to `--only` (list `landing` first, because it signs in):

```powershell
node scripts/pitch_video/record.mjs --work tmp/video-preview --base http://127.0.0.1:8793 --only landing,treasury --ffmpeg <path>
```

## Honesty notes

- Everything shown is the synthetic sandbox.
- The assistant scene shows the deterministic local agent, labelled as such in the UI.
- The own-AI scores are quoted exactly as in README.md, with their synthetic scope.
- The `own-ai-gpu` scene stays disabled until GPU-training evidence is documented.
