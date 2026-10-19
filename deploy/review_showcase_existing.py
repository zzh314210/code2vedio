"""Recheck explicitly selected rendered revisions, retaining every old opinion.

Use after actual visual inspection; never manufactures an approval. Every
selected frame set is reviewed again by the configured vision model, including
the corroboration pass used in production. Compose only if all sections pass.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config
from video_project import restore_credentials,write_json
from pipeline import VideoPipeline
from execution import project_lock
from media import sample_beat_frames,probe
p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('--revision',type=int,required=True);p.add_argument('--render-as',type=int,help='Render archived code into a NEW revision after an infrastructure fix');a=p.parse_args()
project=a.project.resolve();out=project/'output'
manifest=json.loads((out/'manifest.json').read_text())
config=restore_credentials(manifest['config'],load_config(ROOT/'config.local.json'))
pipe=VideoPipeline(manifest['topic'],config,out,project=project,resume=True)
with project_lock(project):
 story=json.loads((out/'storyboard_assets.json').read_text());rendered={}
 for section in story['sections']:
  sid=section['id'];directory=out/sid/f'revision_{a.revision}'
  code=json.loads((out/f'{sid}_code_{a.revision}.json').read_text())
  if (directory/'scene.py').read_text()!=pipe.assemble_code(section,code):raise RuntimeError('Selected scene does not match its archived code and storyboard')
  revision=a.revision
  if a.render_as is not None:
   revision=a.render_as
   if revision<=a.revision or (out/sid/f'revision_{revision}').exists():raise RuntimeError('Rerender must use a new, unused revision')
   write_json(out/f'{sid}_code_{revision}.json',code)
   video=pipe.render(section,code,revision)
   write_json(out/sid/f'revision_{revision}'/'render_provenance.json',{'from_revision':a.revision,'reason':'Explicit rerender of identical archived code with bounded encoder queue; no model code rewrite'})
  else:
   videos=list((directory/'media').rglob('lesson.mp4'))
   if len(videos)!=1:raise RuntimeError('Selected revision has no unique complete video')
   video=videos[0]
  if abs(probe(video)['duration']-sum(b['duration'] for b in section['beats']))>.12:raise RuntimeError('Selected revision is incomplete')
  frames=sample_beat_frames(video,out/sid/f'acceptance_review_{revision}',section['beats'],12)
  timestamps=json.loads((frames[0].parent/'timestamps.json').read_text());pipe.active_stage='review'
  result=pipe.assess_visual(section,frames,timestamps);result['reviewed_revision']=revision
  index=max([98]+[int(f.stem.rsplit('_',1)[1]) for f in out.glob(f'{sid}_review_*.json')])+1
  write_json(out/f'{sid}_review_{index}.json',result)
  print(sid,json.dumps(result,ensure_ascii=False),flush=True)
  if result['has_issues']:raise RuntimeError('Selected revision still has corroborated issues; not composing')
  rendered[sid]={'video':str(video),'revision':revision};write_json(out/f'{sid}_code.json',code)
 write_json(out/'reviewed.json',rendered)
 if a.render_as is not None:write_json(out/'rendered.json',rendered)
result=pipe.run()
write_json(project/'showcase_receipt.json',{'template':pipe.config['task']['template_id'],'status':'generated','result':str(result),'human_review':'pending final playback; re-reviewed selected original geometry after inspecting earlier feedback'})
print('REVIEWED AND COMPOSED',result,flush=True)
