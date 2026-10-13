"""Create renderer scene timings only from successful measured narration takes."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRODUCTION=HERE.parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenes',type=Path,default=PRODUCTION/'script/scenes.json')
    p.add_argument('--manifest',type=Path,default=PRODUCTION/'audio-ai/audio-manifest.json')
    p.add_argument('--output',type=Path,default=HERE/'timed-scenes.json')
    p.add_argument('--scene-ids',help='Explicit comma-separated scene ids for an accurately labelled partial preview.')
    p.add_argument('--lead',type=float,default=.30)
    p.add_argument('--tail',type=float,default=.65)
    p.add_argument('--fps',type=int,default=25)
    args=p.parse_args()
    source=json.loads(args.scenes.read_text(encoding='utf-8-sig'))
    manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    audio={s['scene_id']:s for s in manifest.get('scenes',[]) if s.get('status')=='generated'}
    requested=args.scene_ids.split(',') if args.scene_ids else None
    selected=[s for s in source['scenes'] if not requested or s['id'] in requested]
    if not selected:raise SystemExit('No matching scenes selected.')
    missing=[s['id'] for s in selected if s['id'] not in audio]
    if missing:raise SystemExit('Missing completed narration for: '+', '.join(missing))
    elapsed=0
    for i,scene in enumerate(selected):
        take=audio[scene['id']]
        voice=PRODUCTION/take.get('wav_file',take['file'])
        if not voice.exists():raise SystemExit('Missing audio file: '+str(voice))
        seconds=math.ceil((float(take['duration_seconds'])+args.lead+args.tail)*args.fps)/args.fps
        scene['duration']=seconds
        scene['start_seconds']=round(elapsed,3)
        scene['end_seconds']=round(elapsed+seconds,3)
        scene['voice_file']=str(voice.resolve())
        scene['voice_lead_seconds']=args.lead
        # Mapping remains stable even when a subset is selected.
        kinds=['problem','product','waterfall','records','timeline','comparison','workflow','execution','security','assistant','verification','closing']
        original_index=source['scenes'].index(scene)
        scene['scene_kind']=kinds[original_index] if original_index<len(kinds) else 'closing'
        elapsed+=seconds
    source['scenes']=selected
    source['target_seconds']=round(elapsed,3)
    source['partial_preview']=bool(requested)
    source['voice_note']=manifest.get('voice_note','Supplied narration; use the documented narrator identity.')
    source['voice']=manifest.get('voice')
    source['narration_generation_source']=manifest.get('generation_source')
    source['voice_policy']='Use only these measured narration takes; do not mix narrator identities.'
    source['audio_timing_status']='Measured and aligned to the completed supplied takes.'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(source,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'output':str(args.output.resolve()),'scenes':len(selected),'seconds':round(elapsed,3),'partial_preview':bool(requested)}))

if __name__=='__main__':main()
