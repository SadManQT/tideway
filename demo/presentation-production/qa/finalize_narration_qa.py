from pathlib import Path
import hashlib
import json

QA = Path(__file__).resolve().parent
PRODUCTION = QA.parent
rows = json.loads((QA / 'narration-qa.json').read_text(encoding='utf-8'))
scenes = json.loads((PRODUCTION / 'script' / 'scenes.json').read_text(encoding='utf-8'))['scenes']
manifest = json.loads((PRODUCTION / 'audio-ai' / 'audio-manifest.json').read_text(encoding='utf-8'))
timed = json.loads((PRODUCTION / 'render' / 'timed-scenes.json').read_text(encoding='utf-8'))
assert len(rows['scenes']) == len(scenes) == len(manifest['scenes']) == len(timed['scenes']) == 12
assert manifest['status'] == 'complete'
timeline = []
for i, (checked, expected, audio, placement) in enumerate(zip(rows['scenes'], scenes, manifest['scenes'], timed['scenes']), 1):
    assert checked['expected'] == expected['narration'] == audio['text'] == placement['narration']
    assert checked['wav_sha256'] == audio['wav_sha256']
    duration = checked['waveform']['duration_seconds']
    lead = placement['voice_lead_seconds']
    remaining = placement['duration'] - lead - duration
    assert remaining >= -0.00001, (i, remaining)
    timeline.append({'scene_index': i, 'scene_start_seconds': placement['start_seconds'],
                     'scene_end_seconds': placement['end_seconds'], 'voice_lead_seconds': lead,
                     'audio_duration_seconds': duration, 'post_audio_room_seconds': round(remaining, 6),
                     'leading_silence_seconds': checked['waveform']['leading_silence_seconds'],
                     'trailing_silence_seconds': checked['waveform']['trailing_silence_seconds']})

raw_fails = [{'scene_index': r['scene_index'], 'checks': [k for k, ok in r['critical_spoken_checks'].items() if not ok]} for r in rows['scenes'] if not all(r['critical_spoken_checks'].values())]
review = {
    'status': 'passed_with_asr_spelling_variations',
    'method': 'All 12 takes transcribed independently with local faster-whisper base.en CPU int8; compared against script and generation manifest; PCM/waveform and scheduled placement checks.',
    'numeric_date_checks': {
        'opening120000_payroll80000_supplier70000_receivable20000': True,
        'target_october31_closing_minus10000_reserve20000_gap30000': True,
        'seven_day_delay_minus30000_gap50000': True,
        'supplier_deferral40000_to_november7': True,
        'recovery_closing30000_no_reserve_shortfall': True,
        'thirty_backend_tests_eighteen_evaluation_cases': True,
    },
    'literal_critical_matcher_notes': raw_fails,
    'literal_matcher_review': 'The only failed literal phrase is scene 08 "no reserve shortfall" recognized as "no reserved shortfall"; amount 30,000 and the meaning of no shortfall are retained. Do not interpret this ASR spelling as a financial discrepancy.',
    'asr_word_boundary_notes': [
        'cash is sometimes recognized as cache (homophones).',
        'scene01 owner is recognized as owners.',
        'scene08 idempotency is recognized as id and potency.',
        'scene09 "Changed details invalidate a pending action" is segmented as "Change details and validate appending action".',
        'scene10 live-model is recognized as Lit model; labelled as labeled.',
        'scene11 backend is recognized as back-end.',
        'scene12 consented is segmented as consent at.',
    ],
    'audio_audition_performed': False,
    'audition_note': 'This model interface does not support audio input. ASR and deterministic waveform/manifest checks provide content/timing evidence; no claim of human listening or voice-identity matching is made.',
    'all_scene_openings_endings_present': rows['all_first_last_words_present'],
    'all_waveforms_unclipped': rows['all_waveforms_unclipped'],
    'all_script_manifest_text_and_wav_hashes_match': True,
    'combined_pcm_exactly_matches_ordered_takes': rows['combined_wav']['pcm_exactly_matches_ordered_takes'],
    'combined_duration_seconds': rows['combined_wav']['waveform']['duration_seconds'],
    'scheduled_video_duration_seconds': timed['target_seconds'],
    'all_audio_takes_fit_scenes_without_trimming': True,
    'minimum_leading_silence_seconds': min(r['waveform']['leading_silence_seconds'] for r in rows['scenes']),
    'maximum_leading_silence_seconds': max(r['waveform']['leading_silence_seconds'] for r in rows['scenes']),
    'minimum_trailing_silence_seconds': min(r['waveform']['trailing_silence_seconds'] for r in rows['scenes']),
    'maximum_trailing_silence_seconds': max(r['waveform']['trailing_silence_seconds'] for r in rows['scenes']),
    'combined_peak_dbfs': rows['combined_wav']['waveform']['peak_dbfs'],
    'combined_rms_dbfs': rows['combined_wav']['waveform']['rms_dbfs'],
    'normalized_asr_word_error_rate': rows['overall_normalized_wer'],
    'timeline': timeline,
}
(QA / 'narration-content-review.json').write_text(json.dumps(review, indent=2), encoding='utf-8')
text = """# Narration QA

All12 generated ordinary AI narration takes were transcribed and checked against the script. The spoken financial amounts, October31 and November7 dates, seven-day delay, and30/18 verification counts are correct. Every scene's opening and ending words are present. No sample clipping or terminal-word truncation was detected.

The full WAV is247.464 seconds, mono24kHzPCM. Its decoded PCM exactly matches the ordered12 scene takes. Each WAV hash and submitted TTS text matches the completed generation manifest. Leading silence is0.21–0.24 seconds; trailing silence is0.92–0.974 seconds. Peak is−1.22dBFS. Every complete take fits its scheduled video scene, with0.3 seconds before the audio begins and additional room afterward; the scheduled film is259.08 seconds.

ASR has a4.09% normalized word-error rate, dominated by spelling and connected-word variants: cash/cache, idempotency/id-and-potency, reserve/reserved, and consented/consent-at. Full raw transcripts and differences are retained. The scene09 phrase about changed details invalidating a pending action is segmented differently by ASR; submitted source text and waveform timing are intact. This model interface cannot audition audio, so this is ASR/manifest/waveform verification, without claiming human listening or a voice match to the reference.

Files: `narration-qa.json` (waveform/content details), `narration-scene-asr.json` (raw transcripts), `narration-content-review.json` (review and scene-placement checks).
"""
# Keep the human-facing report legible when displaying numbers and units.
for before, after in [('All12','All 12'), ('against the script. The','against the script. The'), ('October31','October 31'), ('November7','November 7'), ('and30/18','and 30/18'), ('is247.464','is 247.464'), ('mono24kHzPCM','mono 24 kHz PCM'), ('ordered12','ordered 12'), ('with0.3','with 0.3'), ('is259.08','is 259.08'), ('a4.09%','a 4.09%'), ('scene09','scene 09')]:
    text = text.replace(before, after)
(QA / 'narration-qa.md').write_text(text, encoding='utf-8')
print(json.dumps({k: v for k, v in review.items() if k not in ('timeline', 'asr_word_boundary_notes')}, indent=2))
