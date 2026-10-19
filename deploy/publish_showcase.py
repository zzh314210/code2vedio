"""Publish an explicitly reviewed real pipeline result, with reproducible provenance.

Run only after inspecting the actual film, content and narration. This command
checks media and model review; it does not replace that human quality decision.
"""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from editing import inspect_media
from video_project import write_json
from video_templates import CATALOG
p=argparse.ArgumentParser();p.add_argument('template',choices=[t['id'] for t in CATALOG]);p.add_argument('project',type=Path);p.add_argument('--review-note',required=True);a=p.parse_args()
project=a.project.resolve();receipt=json.loads((project/'showcase_receipt.json').read_text());video=project/'output/final.mp4'
if receipt['status']!='generated' or receipt['template']!=a.template:raise SystemExit('No matching successful generation receipt')
# Review records must match the rendered revision, as tracked by the pipeline.
manifest=json.loads((project/'output/manifest.json').read_text())
if manifest.get('status')!='complete' or manifest.get('visual_review',{}).get('passed') is not True:
 raise SystemExit('Current final revisions have not passed visual review')
if not (project/'output/final.mp4').is_file():raise SystemExit('Final video missing')
info=inspect_media(video,max_seconds=600)
if min(info['width'],info['height'])<1080:raise SystemExit('Sample must be native 1080p')
if len(a.review_note.strip())<20:raise SystemExit('Record factual and visual review, not merely success')
subprocess.run(['ffmpeg','-v','error','-nostdin','-threads','1','-i',str(video),'-f','null','-'],check=True,timeout=240)
out=ROOT/'web/public/showcase';out.mkdir(parents=True,exist_ok=True)
shutil.copy2(video,out/(a.template+'.mp4'))
subprocess.run(['ffmpeg','-v','error','-y','-ss',str(min(4,info['duration']/3)),'-i',str(video),'-frames:v','1','-vf','scale=960:-2','-threads','1',str(out/(a.template+'.jpg'))],check=True,timeout=45)
record={'template':a.template,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'duration':info['duration'],'review_note':a.review_note.strip(),'project':project.name,'review':'accepted after actual film inspection'}
write_json(project/'showcase_acceptance.json',record)
write_json(out/(a.template+'.json'),record)
t=next(t for t in CATALOG if t['id']==a.template);catalog=ROOT/'templates/showcase.json';entries=json.loads(catalog.read_text())
entry={'id':a.template,'title':t['title'],'description':a.review_note.strip(),'credit':'实际制作示例 · 2026-10-19','license':'详见示例素材来源说明','source':'/showcase/SOURCES.md','duration':round(info['duration']),'kind':'creation'}
entries=[e for e in entries if e['id']!=a.template]+[entry];write_json(catalog,entries)
print('Published reviewed sample:',a.template,round(info['duration'],2),'seconds')
