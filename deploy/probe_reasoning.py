"""Small authorized real probes; no credentials in output or reports."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config,sanitize_error
from model_gateway import ModelGateway
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'.tmp/truth-upgrade/gateway-probes.json');a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
c=load_config(ROOT/'config.local.json');results=[]
for model in ['deepseek-v4.1-flash-1013','deepseek-v4.1-flash-1017','kimi-k3']:
 s={**c['text'],'model':model,'fallback_models':[],'provider':'dashscope','thinking_enabled':True,'reasoning_effort':'max','stream':False,'max_tokens':4096,'token_parameter':'max_tokens','max_retries':0,'usage_file':str(a.output.with_suffix('.usage.jsonl')),'reasoning_audit_file':str(a.output.with_suffix('.requests.jsonl'))}
 g=ModelGateway(s)
 try:
  text,usage=g.request('18减12是多少？只输出JSON：{"answer":数字}。')
  assert json.loads(text)['answer']==6
  r={'model':model,'ok':True,'answer':6,'usage':usage,'sent_reasoning':g.settings.get('effective_reasoning')}
 except Exception as e:r={'model':model,'ok':False,'status':getattr(e,'status_code',None),'error':sanitize_error(str(e),c)[:600]}
 finally:g.client.close()
 results.append(r);a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False),flush=True)
