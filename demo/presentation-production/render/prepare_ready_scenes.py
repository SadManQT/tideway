"""Prepare stable visual asset references; audio timing stays explicitly pending."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent
PRODUCTION=ROOT.parent
source=json.loads((PRODUCTION/'script/scenes.json').read_text(encoding='utf-8-sig'))
kinds=['problem','product','waterfall','records','timeline','comparison','workflow','execution','security','assistant','verification','closing']
asset_names=[[],['overview.png'],['overview.png'],['records.png','import-preview.png'],['overview.png'],
             ['plans.png'],['approved.png','consent.png'],['executed.png','readback.png','recovered-overview.png'],
             ['activity.png'],['assistant.png'],[],[]]
for i,scene in enumerate(source['scenes']):
    scene['scene_kind']=kinds[i]
    scene['ui_assets']=[str((PRODUCTION/'assets'/a).resolve()) for a in asset_names[i]]
source['audio_timing_status']='Pending measured complete narration; run assemble_timed_scenes.py before final rendering.'
source['voice_policy']='Use only the selected supplied narration takes; do not mix narrator identities.'
source['renderer']='render/render_presentation.py'
(ROOT/'ready-scenes.json').write_text(json.dumps(source,indent=2,ensure_ascii=False),encoding='utf-8')
print('Prepared',ROOT/'ready-scenes.json')
