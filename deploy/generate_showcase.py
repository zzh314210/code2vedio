"""Real template acceptance using explicitly authorized local channels, no secret output."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'deploy'))
from configuration import load_config,sanitize_error
from test_local_models import task_config
from video_templates import CATALOG
import httpx
p=argparse.ArgumentParser();p.add_argument('template',choices=[x['id'] for x in CATALOG]);p.add_argument('--base',default='http://127.0.0.1:7860');a=p.parse_args()
t=next(x for x in CATALOG if x['id']==a.template)
local=load_config(ROOT/'config.local.json');config=task_config(local)
config['text'].update(model='kimi-k3',fallback_models=['deepseek-v4.1-flash-1017'])
config['vision'].update(model='deepseek-v4.1-flash',fallback_models=['qwen3.8-flash'])
creds=dict(x.split('=',1) for x in (ROOT/'private/admin-access.txt').read_text().splitlines())
with httpx.Client(base_url=a.base,timeout=45,trust_env=False,headers={'X-Frame-Request':'1'}) as c:
 r=c.post('/api/auth/login',json={'username':creds['USERNAME'],'password':creds['PASSWORD']});r.raise_for_status()
 try:
  r=c.post('/api/jobs',json={'prompt':t['example_prompt'],'template_id':t['id'],'style':t['style'],'duration':t['duration'],'auto_approve':True,'config':config})
  if r.is_error:raise RuntimeError(sanitize_error(r.text,local)[:500])
  out=ROOT/'.tmp/showcase';out.mkdir(parents=True,exist_ok=True)
  (out/(t['id']+'.json')).write_text(json.dumps({'template_id':t['id'],'job_id':r.json()['id'],'models':{role:{'model':config[role]['model'],'fallback_models':config[role]['fallback_models']} for role in ['text','vision']}},ensure_ascii=False,indent=2))
  print(t['id'],r.json()['id'])
 finally:c.post('/api/auth/logout')
