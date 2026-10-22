"""Wire-format and accounting tests; no network or real credentials."""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from model_gateway import ModelGateway
from provider_protocols import reasoning_body
from configuration import resolve_config
for provider in ['dashscope','deepseek','moonshot','doubao','zhipu','minimax','openai']:
 body,p=reasoning_body({'provider':provider,'protocol':'chat_completions','model':'model'},24000)
 assert p['enabled'] and p['requested_effort']=='max'
 if provider=='deepseek':assert body=={'thinking':{'type':'enabled'},'reasoning_effort':'max'}
 if provider=='doubao':assert body['reasoning_effort']=='high'
 if provider=='moonshot':assert 'reasoning_effort' not in body
body,p=reasoning_body({'provider':'anthropic','protocol':'anthropic','model':'claude-sonnet-4-5'},24000)
assert body['thinking']['budget_tokens']==22976
with tempfile.TemporaryDirectory() as directory:
 events=[]
 def respond(request):
  data=json.loads(request.content);events.append((request,data))
  assert request.url.path=='/v1/messages'
  assert request.headers['x-api-key']=='fake-secret'
  assert request.headers['anthropic-version']=='2023-06-01'
  assert data['thinking']=={'type':'adaptive'} and data['output_config']['effort']=='max'
  return httpx.Response(200,json={'id':'native-test','model':'claude-opus-4-6','stop_reason':'end_turn','content':[{'type':'thinking','thinking':'private'},{'type':'text','text':'{"answer":6}'}],'usage':{'input_tokens':21,'output_tokens':7}})
 c=resolve_config({'text':{'base_url':'https://example.com/v1','model':'claude-opus-4-6','api_key':'fake-secret','provider':'anthropic','protocol':'anthropic','max_tokens':24000,'usage_file':str(Path(directory)/'usage.jsonl')}})
 g=ModelGateway(c['text']);g.client._client.close();g.client._client=httpx.Client(transport=httpx.MockTransport(respond))
 assert g.json('test')['answer']==6
 usage=json.loads(Path(c['text']['usage_file']).read_text());assert usage['input_tokens']==21 and usage['output_tokens']==7 and 'private' not in json.dumps(usage)
 g.client.close()
print('PASS: provider request bodies, max mapping, native Claude auth/payload/usage, private reasoning excluded')
for model,expected in [('o3','high'),('gpt-5.1','high'),('gpt-5.4','xhigh'),('gpt-6','max')]:
 for protocol in ('responses','chat_completions'):
  body,p=reasoning_body({'provider':'openai','model':model,'protocol':protocol},24000)
  assert p['requested_effort']=='max' and p['effective_effort']==expected
body,p=reasoning_body({'provider':'openai','model':'gpt-4.1','thinking_enabled':False},24000);assert body=={}
try:reasoning_body({'provider':'openai','model':'gpt-4.1'},24000)
except ValueError:pass
else:raise AssertionError('Nonreasoning model advertised maximum thinking')
print('PASS: OpenAI known model capabilities map Max explicitly; nonreasoning models rejected before calls')
