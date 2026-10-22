"""Generate a verified logic lesson through the real production pipeline.

Uses authorized local credentials without printing them. Test usage stays in
its own project; it is never attributed to a production user's balance.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config,sanitize_error,merge
from video_templates import apply_template,CATALOG
from pipeline import VideoPipeline
p=argparse.ArgumentParser();p.add_argument('--question',type=Path);p.add_argument('--name',default='truth-teaching-v1');p.add_argument('--resume',action='store_true');p.add_argument('--stop-after',default='compose');a=p.parse_args()
project=ROOT/'video_projects'/a.name
if project.parent!=ROOT/'video_projects':raise SystemExit('Invalid project name')
question=a.question.read_text() if a.question else next(t for t in CATALOG if t['id']=='truth_logic')['example_prompt']
c=load_config(ROOT/'config.local.json',overrides={'text':{'model':'deepseek-v4.1-flash-1017','fallback_models':['kimi-k3'],'provider':'dashscope','thinking_enabled':True,'reasoning_effort':'max','max_tokens':24000,'timeout':180,'max_retries':0,'reasoning_audit_file':str(project/'output/reasoning_audit.jsonl'),'usage_file':str(project/'output/model_usage.jsonl')},'vision':{'model':'deepseek-v4.1-flash','fallback_models':['qwen3.8-flash'],'provider':'dashscope','thinking_enabled':True,'reasoning_effort':'max','max_tokens':10000,'stream':True,'enabled':True,'inherit_text':False,'frames':18,'rounds':0,'require_pass':True,'usage_file':str(project/'output/model_usage.jsonl'),'reasoning_audit_file':str(project/'output/reasoning_audit.jsonl')},'tts':{'provider':'edge','voice':'zh-CN-YunxiNeural'},'style':'studio_sketch','video':{'quality':'high','fps':30,'target_duration':120,'max_sections':2,'max_beats':6,'render_timeout':900,'pause_seconds':.2},'teaching_research':{'enabled':False},'assets':{'enabled':False}})
c=apply_template(c,'truth_logic')
if a.resume:
 frozen=json.loads((project/'output/manifest.json').read_text())['config']
 # Keep the archived editorial/config version; restore only authorized secrets.
 c=merge(c,frozen)
 local=load_config(ROOT/'config.local.json')
 for role in ('text','vision'):c[role]['api_key']=local[role]['api_key']
try:
 out=VideoPipeline(question,c,project/'output',project=project,resume=a.resume,on_event=lambda e:print(json.dumps(e,ensure_ascii=False),flush=True)).run(stop_after=a.stop_after)
 print('RESULT',out,flush=True)
except Exception as e:print(sanitize_error(str(e),c),flush=True);raise
