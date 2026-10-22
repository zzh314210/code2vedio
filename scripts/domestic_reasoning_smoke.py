"""Model-specific contracts and actual outbound bodies; no paid calls."""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import resolve_config
from model_gateway import ModelGateway
from provider_protocols import reasoning_body

cases=[
 ('deepseek','deepseek-flash',{'thinking':{'type':'enabled'},'reasoning_effort':'max'},'max'),
 ('moonshot','kimi-k3',{'reasoning_effort':'max'},'max'),
 ('moonshot','kimi-k2.6',{'thinking':{'type':'enabled'}},None),
 ('zhipu','glm-5.3',{'thinking':{'type':'enabled'},'reasoning_effort':'max'},'max'),
 ('zhipu','glm-5.2',{'thinking':{'type':'enabled'},'reasoning_effort':'max'},'max'),
 ('zhipu','glm-4.7',{'thinking':{'type':'enabled'}},None),
 ('minimax','MiniMax-M3.1-Flash',{'reasoning_split':True,'reasoning_effort':'max'},'max'),
 ('minimax','MiniMax-M2.7',{'reasoning_split':True},None),
 ('dashscope','deepseek-v4.1-flash-1017',{'enable_thinking':True,'reasoning_effort':'max'},'max'),
 ('dashscope','kimi-k3',{'enable_thinking':True,'reasoning_effort':'max'},'max'),
 ('dashscope','qwen3.8-flash',{'enable_thinking':True,'reasoning_effort':'xhigh'},'xhigh'),
 ('dashscope','qwen3.8-omni-flash',{'enable_thinking':True,'reasoning_effort':'xhigh'},'xhigh'),
 ('dashscope','qwen3.7-flash',{'enable_thinking':True},None),
 ('dashscope','MiniMax/MiniMax-M3.1-Flash',{'thinking':{'type':'adaptive'},'reasoning_effort':'max'},'max'),
]
with tempfile.TemporaryDirectory() as temp:
 for provider,model,wanted,level in cases:
  settings={'provider':provider,'model':model,'protocol':'chat_completions','api_key':'fixture-key','base_url':'https://example.com/v1','stream':False,'extra_body':{'thinking_budget':123,'reasoning_split':False,'reasoning_effort':'low'}}
  body,policy=reasoning_body(settings,24000)
  assert body==wanted,(provider,model,body)
  if level:assert policy['effective_effort']==level
  else:assert 'model-default' in policy['effective_effort']
  c=resolve_config({'text':{**settings,'usage_file':str(Path(temp)/'usage.jsonl')}})
  def respond(request):
   payload=json.loads(request.content)
   assert request.url.path=='/v1/chat/completions'
   if provider=='dashscope' and model.startswith('qwen3.8'):
    assert 'max_completion_tokens' in payload and 'max_tokens' not in payload
   for key in ('thinking','reasoning_effort','enable_thinking','reasoning_split','thinking_budget'):
    assert (key in payload)==(key in wanted),(model,key,payload)
    if key in wanted:assert payload[key]==wanted[key]
   return httpx.Response(200,json={'id':'probe','model':model,'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'{"answer":6}','reasoning_content':'private'}}],'usage':{'prompt_tokens':3,'completion_tokens':8,'total_tokens':11}})
  g=ModelGateway(c['text']);g.client._client.close();g.client._client=httpx.Client(transport=httpx.MockTransport(respond))
  assert g.json('fixture')['answer']==6;g.client.close()
  assert 'private' not in Path(c['text']['usage_file']).read_text()

for provider,model,wanted in [('deepseek','deepseek-flash','high'),('moonshot','kimi-k3','high'),('zhipu','glm-5.3','high'),('zhipu','glm-5.2','high'),('dashscope','kimi-k3','high'),('dashscope','qwen3.8-flash','medium')]:
 body,policy=reasoning_body({'provider':provider,'model':model,'reasoning_effort':'medium'},24000)
 assert body['reasoning_effort']==wanted and policy['effective_effort']==wanted
assert reasoning_body({'provider':'zhipu','model':'glm-5.2','reasoning_effort':'low'},24000)[0]['reasoning_effort']=='high'
assert reasoning_body({'provider':'zhipu','model':'glm-5.3','reasoning_effort':'low'},24000)[0]['reasoning_effort']=='low'
assert reasoning_body({'provider':'dashscope','model':'kimi/kimi-k3','reasoning_effort':'low'},24000)[0]['reasoning_effort']=='max'
for provider,model in [('moonshot','kimi-k3'),('moonshot','kimi-k2.7-code'),('zhipu','glm-5.3'),('minimax','MiniMax-M3.1-Flash'),('minimax','MiniMax-M2.7'),('dashscope','glm-5.3'),('dashscope','kimi/kimi-k3')]:
 try:reasoning_body({'provider':provider,'model':model,'thinking_enabled':False},24000)
 except ValueError:pass
 else:raise AssertionError('always-thinking model accepted disabled: '+model)
assert reasoning_body({'provider':'dashscope','model':'kimi-k3','thinking_enabled':False},24000)[0]=={'enable_thinking':False}
for provider,model,levels in [
 ('moonshot','kimi-k3',['low','high','high','max']),
 ('zhipu','glm-5.2',['high','high','high','max']),
 ('zhipu','glm-5.3',['low','high','high','max']),
 ('minimax','MiniMax-M3.1-Flash',['low','medium','high','max']),
 ('dashscope','qwen3.8-flash',['low','medium','xhigh','xhigh'])]:
 for requested,sent in zip(('low','medium','high','max'),levels):
  body,policy=reasoning_body({'provider':provider,'model':model,'reasoning_effort':requested},24000)
  assert body['reasoning_effort']==sent and policy['effective_effort']==sent
# Never let a protocol selector bypass the native contract and start billing.
c=resolve_config({'text':{'provider':'moonshot','model':'kimi-k3','protocol':'responses','api_key':'fixture-key'}})
g=ModelGateway(c['text'])
with patch('model_gateway.billing_call') as bill:
 try:g._request('fixture')
 except ValueError:pass
 else:raise AssertionError('native protocol mismatch accepted')
 bill.assert_not_called()
g.client.close()
print('PASS: 14 native/hosted request bodies, four effort levels and mappings, old-model switch-only policy, invalid disable/protocol rejected before billing, no private reasoning stored')
