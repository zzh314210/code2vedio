"""Usage is retained for successful, invalid and truncated model output; no remote calls."""
import sys,tempfile,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from model_gateway import ModelGateway
from public_transport import PublicTransport
import httpx
with tempfile.TemporaryDirectory() as tmp:
 config={'protocol':'chat_completions','model':'test-model','base_url':'https://example.com/v1','api_key':'test-secret','usage_file':str(Path(tmp)/'usage.jsonl')}
 gateway=ModelGateway(config)
 usage=NS(prompt_tokens=100,completion_tokens=30,prompt_tokens_details={'cached_tokens':40})
 for finish,content in [('stop','valid'),('length','truncated'),('stop','')]:
  response=NS(id='test-response-'+finish,model='test-model',usage=usage,choices=[NS(finish_reason=finish,message=NS(content=content))])
  with patch.object(gateway.client.chat.completions,'create',return_value=response):
   try:gateway.request('test prompt')
   except ValueError:pass
 events=[json.loads(line) for line in Path(config['usage_file']).read_text().splitlines()]
 assert len(events)==3 and all(e['input_tokens']==100 and e['cached_input_tokens']==40 for e in events)
 assert len({e['id'] for e in events})==3
 from usage_meter import record_usage
 record_usage(config,'text',{})
 assert not json.loads(Path(config['usage_file']).read_text().splitlines()[-1])['metered']
 # Streaming vendors may return a billable model alias different from the request.
 gateway.settings={**gateway.settings,'stream':True}
 class Chunks:
  def __iter__(self):
   yield NS(id='stream-response-123',model='actual-billed-model',usage=None,choices=[NS(delta=NS(content='valid'),finish_reason='stop')])
   yield NS(id='stream-response-123',model='actual-billed-model',usage=usage,choices=[])
  def close(self):pass
 with patch.object(gateway.client.chat.completions,'create',return_value=Chunks()):
  assert gateway.request('streaming test')[0]=='valid'
 event=json.loads(Path(config['usage_file']).read_text().splitlines()[-1])
 assert event['model']=='actual-billed-model' and event['response_id']=='stream-response-123'
 assert event['input_tokens']==100 and event['output_tokens']==30
 # Invalid cache counts must not be silently clamped into a billable amount.
 record_usage(config,'text',{'prompt_tokens':10,'completion_tokens':5,'prompt_tokens_details':{'cached_tokens':11}})
 assert not json.loads(Path(config['usage_file']).read_text().splitlines()[-1])['metered']
 # Model requests reserve from a conservative text bound and expose stage/timing.
 from billing_client import BillingError
 captures=[]
 with patch('model_gateway.billing_call',side_effect=lambda settings,op,data:captures.append((op,data)) or {'billing':False}),patch.object(gateway.client.chat.completions,'create',return_value=Chunks()):
  gateway.request('中文 prompt')
 assert captures[0][1]['input_bound']==len('中文 prompt'.encode('utf8'))+1024
 assert event['duration_ms']>=0
 gateway.client.close()
 # Signed personal API configuration bypasses both the credit service and local
 # usage files, even when a legacy task still carries billing paths/context.
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
 from user_config import runtime_config
 from configuration import DEFAULTS,public_config
 from billing_client import call as bill
 personal={'use_platform':False,'text':{**config,'platform_billing':True},'vision_inherit':True}
 runtime=runtime_config(DEFAULTS,personal,Path(tmp)/'library.sqlite3')
 for role in ('text','vision'):
  channel=runtime[role]
  channel['usage_file']=str(Path(tmp)/(role+'-byok.jsonl'))
  channel['billing_context']={'private':str(Path(tmp)/'unavailable-billing-service'),'user_id':'own-user','job_id':'own-job'}
  assert channel['platform_billing'] is False
  assert 'platform_billing' not in public_config(channel),'Runtime billing policy changed the content cache'
  own=ModelGateway(channel,role)
  response=NS(id='own-response',model=channel['model'],usage=usage,choices=[NS(finish_reason='stop',message=NS(content='personal response'))])
  with patch('billing_client.httpx.Client',side_effect=AssertionError('BYOK contacted local billing')),patch.object(own.client.chat.completions,'create',return_value=response):
   assert own.request('no prepayment required')[0]=='personal response'
   assert bill(channel,'authorize',{'id':'own-call'})=={'billing':False}
   record_usage(channel,role,extra={'error_type':'TimeoutError'})
  assert not Path(channel['usage_file']).exists(),'BYOK wrote local usage records'
  own.client.close()
 platform=runtime_config(DEFAULTS,{**personal,'use_platform':True},Path(tmp)/'library.sqlite3')
 assert platform['text']['platform_billing'] and platform['vision']['platform_billing']
 assert not platform['tts']['platform_billing']
 paid={**config,'platform_billing':True,'usage_file':str(Path(tmp)/'platform.jsonl')}
 with patch('usage_meter.billing_call',return_value={'billing':True}) as settle:
  record_usage(paid,'text',usage)
  settle.assert_called_once()
 assert Path(paid['usage_file']).is_file(),'Platform metering was disabled'
 transport=PublicTransport()
 with patch('public_transport.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
  try:transport.handle_request(httpx.Request('POST','https://example.com/v1'))
  except ValueError:pass
  else:raise AssertionError('DNS rebound to private address was accepted')
 transport.close()
print('PASS: platform usage retained before validation failures; BYOK bypasses billing and usage files; cache identity unchanged; private DNS targets rejected.')
