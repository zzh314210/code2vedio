"""Produce a real sample via the Code2Video pipeline without changing live services."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config,merge,sanitize_error
from video_templates import CATALOG,apply_template
from pipeline import VideoPipeline
from video_project import write_json
p=argparse.ArgumentParser();p.add_argument('template',choices=[t['id'] for t in CATALOG]);p.add_argument('--resume',action='store_true');p.add_argument('--revision',default='v2');p.add_argument('--material',action='append',default=[]);a=p.parse_args()
t=next(t for t in CATALOG if t['id']==a.template)
c=load_config(ROOT/'config.local.json',overrides={'text':{'model':'kimi-k3','fallback_models':['deepseek-v4.1-flash-1017']},'vision':{'model':'deepseek-v4.1-flash','fallback_models':['qwen3.8-flash'],'enabled':True,'inherit_text':False,'frames':12,'rounds':2,'require_pass':True},'tts':{'provider':'edge','voice':'zh-CN-YunxiNeural'},'style':t['style'],'video':{'quality':'high','fps':30,'target_duration':t['duration'],'max_sections':min(6,max(1,__import__('math').ceil(t['duration']/60))),'max_beats':6,'render_timeout':900,'pause_seconds':.15},'assets':{'enabled':False,'max_per_section':6},'teaching_research':{'enabled':False}})
c=apply_template(c,t['id']);project=ROOT/'video_projects'/('showcase-'+t['id']+'-'+a.revision)
def event(e):print(json.dumps(e,ensure_ascii=False),flush=True)
try:
 result=VideoPipeline(t['example_prompt'],c,project/'output',project=project,materials=[ROOT/x for x in t.get('example_materials',[])]+[Path(x) for x in a.material],resume=a.resume,on_event=event).run()
 write_json(project/'showcase_receipt.json',{'template':t['id'],'result':str(result),'status':'generated','human_review':'pending'})
 print('SAMPLE GENERATED',str(result),flush=True)
except Exception as error:
 print('SAMPLE INCOMPLETE',sanitize_error(str(error),c)[:1200],flush=True);sys.exit(1)
