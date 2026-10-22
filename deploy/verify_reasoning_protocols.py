"""Real hosted-model reasoning probes, including invalid-level controls.

Does not print credentials or reasoning text. Small calls use authorized local
configuration and never enter a production user's balance.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config,sanitize_error
from model_gateway import ModelGateway
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'.tmp/truth-upgrade/verified-protocols.json');a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
c=load_config(ROOT/'config.local.json');results=[]
for model in ['deepseek-v4.1-flash-1017','kimi-k3','qwen3.8-flash']:
 s={**c['text'],'model':model,'fallback_models':[],'provider':'dashscope','protocol':'chat_completions','thinking_enabled':True,'reasoning_effort':'max','stream':False,'max_tokens':4096,'token_parameter':'max_tokens','max_retries':0,'usage_file':str(a.output.with_suffix('.usage.jsonl'))}
 g=ModelGateway(s);r={'model':model}
 try:
  text,usage=g.request('18减12是多少？只输出JSON：{"answer":数字}。')
  assert json.loads(text)['answer']==6
  r.update(ok=True,policy=g.settings['effective_reasoning'],usage=usage)
  # An invalid enum should be rejected by an endpoint that validates it.
  # A successful invalid request is reported, never relabeled as proof.
  try:
   bad=g.client.chat.completions.create(model=model,messages=[{'role':'user','content':'18减12是多少？只输出数字。'}],max_tokens=512,extra_body={'enable_thinking':True,'reasoning_effort':'invalid-probe-level'})
   r['invalid_control']={'status':200,'rejected':False,'note':'接口未拒绝非法档位，不能确认强度校验生效','usage':bad.usage.model_dump() if bad.usage else None}
  except Exception as e:
   code=getattr(e,'status_code',None)
   r['invalid_control']={'status':code,'rejected':code in (400,422),'error':sanitize_error(str(e),c)[:500]}
 except Exception as e:r.update(ok=False,error=sanitize_error(str(e),c)[:500],status=getattr(e,'status_code',None))
 finally:g.client.close()
 results.append(r);a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False),flush=True)
