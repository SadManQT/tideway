# Narration QA

All 12 generated ordinary AI narration takes were transcribed and checked against the script. The spoken financial amounts, October 31 and November 7 dates, seven-day delay, and 30/18 verification counts are correct. Every scene's opening and ending words are present. No sample clipping or terminal-word truncation was detected.

The full WAV is 247.464 seconds, mono 24 kHz PCM. Its decoded PCM exactly matches the ordered 12 scene takes. Each WAV hash and submitted TTS text matches the completed generation manifest. Leading silence is0.21–0.24 seconds; trailing silence is0.92–0.974 seconds. Peak is−1.22dBFS. Every complete take fits its scheduled video scene, with 0.3 seconds before the audio begins and additional room afterward; the scheduled film is 259.08 seconds.

ASR has a 4.09% normalized word-error rate, dominated by spelling and connected-word variants: cash/cache, idempotency/id-and-potency, reserve/reserved, and consented/consent-at. Full raw transcripts and differences are retained. The scene 09 phrase about changed details invalidating a pending action is segmented differently by ASR; submitted source text and waveform timing are intact. This model interface cannot audition audio, so this is ASR/manifest/waveform verification, without claiming human listening or a voice match to the reference.

Files: `narration-qa.json` (waveform/content details), `narration-scene-asr.json` (raw transcripts), `narration-content-review.json` (review and scene-placement checks).
