# Probaho motion presentation

The finished video is `../Probaho-presentation.mp4`: a 4 minute 19.08 second narrated English presentation of Probaho's synthetic SME cash-flow recovery workflow. It contains 12 scenes at 1920 x 1080, 25 fps, H.264 video and AAC stereo audio, with fast-start playback.

All twelve scenes use one ordinary AI narrator, Microsoft `en-US-GuyNeural` at rate `-8%`. The supplied `reference.mp4` informed the navy, teal and amber palette, staggered reveals, growing counters and gentle camera motion. The final narrator is the AI voice approved by the user. Original reference speech is not used in the finished video.

The video combines motion graphics with genuine captures of Records, CSV validation, Assistant, human review, simulated supplier consent, execution, atomic read-back and activity evidence. Captures were made against a disposable synthetic database. Financial figures describe the documented Shapla Services fixture: opening BDT 120,000; initial closing BDT -10,000; reserve gap BDT 30,000; deferring BDT 40,000 produces target-date closing BDT 30,000. The deferred obligation remains payable on 7 November. No real payment or supplier contact is shown.

## Editable files

- `script/`: narration and the twelve-scene plan.
- `audio-ai/`: the consistent final AI voice, measured durations and generation code.
- `assets/`: genuine UI captures, the recorded synthetic flow and capture evidence.
- `render/`: editable Python motion renderer and the measured scene timeline.
- `qa/`: narration and encoded-video verification.

Final verification passed: every scene contains motion; the encoded narration matches its exact source take and scheduled offset; the entire video and audio decode without errors. Narration checks confirmed the financial figures and dates, with zero clipped source samples.

The source ZIP contains these final production assets. It excludes credentials, dependency caches, the supplied reference, abandoned voice probes and render intermediates.

## Render on Windows

Use Python 3.11 or newer, FFmpeg, NumPy and Pillow. Windows Segoe UI fonts are used.

```powershell
python -m pip install numpy pillow imageio-ffmpeg
$videoFfmpeg = python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
python render/render_presentation.py --scenes render/timed-scenes-portable.json --ffmpeg $videoFfmpeg --output Probaho-presentation.mp4
```

Run these commands from the extracted `Probaho-presentation` folder. The final narration is already included; no token or online voice generation is needed to render it again. Titles, numerical graphics, timing and UI crop choices are editable in the renderer and scene JSON.

To regenerate speech, see `audio-ai/README.md`. Its online voice service is used through the [edge-tts client](https://github.com/rany2/edge-tts).
