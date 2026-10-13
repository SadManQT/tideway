# Final presentation narrator

All 12 scenes use the same ordinary English AI voice: **Microsoft `en-US-GuyNeural`**, generated through Microsoft Edge online text-to-speech using `edge-tts` 7.3.0. Settings: rate `-8%`, pitch `+0Hz`, volume `+0%`.

The user approved an ordinary AI voice after the reference-cloning public quota was exhausted. This narrator is not the reference speaker. No F5 reference-cloned takes are mixed into these files; those exploratory takes remain separately under `audio/` and `audio-probe/`.

- `scene-01.mp3` through `scene-12.mp3`: narration by scene.
- `wav/scene-01.wav` through `wav/scene-12.wav`: decoded 24 kHz mono PCM versions for exact timing, rendering, and ASR QA.
- `narration-full.wav` and `narration-full.mp3`: complete narration, same scene order, without additional visual holds.
- `audio-manifest.json`: exact text, measured PCM duration, checksums, voice identity, settings, and source.
- `generate_ai_narration.py`: isolated production code, with at most two independent generation requests at a time and no automatic overwrite/retry.

The existing English script and its financial figures remain unchanged. Use measured WAV durations for the edit, adding only the visual hold time needed. Remaining motion design follows the supplied reference's broad pacing and presentation style.

Client source: [edge-tts project](https://github.com/rany2/edge-tts). Voice identity: [Microsoft language and voice support](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts).

For regeneration on another Windows machine, install `edge-tts` and `imageio-ffmpeg` with `python -m pip install edge-tts imageio-ffmpeg`. The generator detects FFmpeg on PATH or through imageio-ffmpeg. Completed, checksum-matching takes are preserved. To create new narration after editing the text, keep a backup and use a separate production folder; the generator refuses to overwrite successful takes.
