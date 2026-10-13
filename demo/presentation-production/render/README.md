# Probaho presentation renderer

Deterministic editable motion graphics, 1920 × 1080 at 25 fps, using Pillow,
NumPy and FFmpeg. The renderer never writes to the application or its database.
It uses genuine fresh UI screenshots plus explanatory graphics for the
documented synthetic Shapla fixture. It does not fabricate an execution receipt.

## Review motion and layout

```powershell
python demo/presentation-production/render/render_presentation.py --preview
python demo/presentation-production/render/render_presentation.py --frames-only
```

The first command creates a 13-second motion preview, not the final narration.
The second creates all scene PNGs and a contact sheet.

## Render the final narration

```powershell
python demo/presentation-production/render/render_presentation.py --scenes demo/presentation-production/render/timed-scenes-portable.json --output demo/Probaho-presentation.mp4
```

Use `--ffmpeg C:/path/to/ffmpeg.exe` if automatic binary detection fails.
No voice is generated or silently substituted. A provided narration track is
muxed as AAC; the video is H.264/YUV420p with fast-start playback.

Scene JSON supports the existing `id`, `title`, `start_seconds`, `end_seconds`
format, or an explicit `duration` and `scene_kind`. Supported kinds are problem,
product, waterfall, records, timeline, comparison, workflow, execution, security,
assistant, verification, closing and screenshot. An explicit `screenshot` path
and `[left, top, right, bottom]` `crop` can override defaults. A `voice_file` on
every scene supplies separate narration takes instead of a global track.

To align the animation with measured completed takes, run
`python demo/presentation-production/render/assemble_timed_scenes.py`.
Its default manifest is the completed ordinary AI voice under `audio-ai/`.
It refuses incomplete narration manifests. For an explicitly partial sample,
pass `--scene-ids 01-problem,02-product --output path/to/intro-scenes.json`.
The helper adds a short visual lead and tail, aligns to exact 25-fps boundaries,
and attaches the supplied voice files. WAV speech is never silently clipped.

Fresh captures are read from `../assets/`, including overview, records, import
preview, assistant, approved review, simulated supplier consent, execution
receipt, atomic read-back and permission events. They transition into focused
UI views alongside large explanatory type, counters and dated nodes.

The source ZIP provides `timed-scenes-portable.json` with relative audio and
asset paths. Use it when rendering from the extracted production folder; see
the top-level README for commands.
