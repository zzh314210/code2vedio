"""Exercise both local fallback chains without making external model requests."""
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import resolve_config
from model_gateway import ModelGateway
from billing_client import BillingError
config=resolve_config({'text':{'protocol':'chat_completions','base_url':'https://example.com/v1','model':'primary','fallback_models':['fallback-1','fallback-2'],'api_key':'synthetic-test-key'},'vision':{'enabled':True,'inherit_text':True}})
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);picture=root/'frame.png';picture.write_bytes(b'test-frame-data')
 for role in ('text','vision'):
  chain=[config[role]['model'],*config[role]['fallback_models']]
  assert len(chain)==3
  settings={**config[role],'api_key':'synthetic-test-key','stream':False,'max_retries':0,'usage_file':str(root/(role+'.jsonl'))}
  gateway=ModelGateway(settings,role);calls=[]
  def respond(**kwargs):
   calls.append(kwargs)
   index=chain.index(kwargs['model'])
   if index==1:raise RuntimeError('simulated upstream unavailable')
   return NS(id='response-'+str(index),model=kwargs['model'],usage=NS(prompt_tokens=10,completion_tokens=2),choices=[NS(finish_reason='length' if index==0 else 'stop',message=NS(content='complete'))])
  with patch.object(gateway.client.chat.completions,'create',side_effect=respond):
   assert gateway.request('same task',images=[picture] if role=='vision' else None)[0]=='complete'
   assert [item['model'] for item in calls]==chain
   assert all(item['messages']==calls[0]['messages'] for item in calls)
   events=[json.loads(line) for line in Path(settings['usage_file']).read_text().splitlines()]
   assert len(events)==3 and len({event['id'] for event in events})==3
   assert [event['metered'] for event in events]==[True,False,True]
   assert [event['requested_model'] for event in events]==chain
   gateway.request('next task',images=[picture] if role=='vision' else None)
   assert calls[-1]['model']==chain[-1]
  # A local billing failure must stop all calls, rather than bypassing it via fallback.
  with patch('model_gateway.billing_call',side_effect=BillingError('test ledger unavailable')),patch.object(gateway.client.chat.completions,'create') as upstream:
   try:gateway.request('must stop')
   except BillingError:pass
   else:raise AssertionError('billing failure was bypassed')
   upstream.assert_not_called()
  gateway.settings={**gateway.settings,'model':chain[0]}
  structured=[]
  def structured_response(**kwargs):
   structured.append(kwargs['model'])
   content='{"accepted": false}' if kwargs['model']==chain[0] else '{"accepted": true}'
   return NS(id='structured-'+kwargs['model'],model=kwargs['model'],usage=NS(prompt_tokens=5,completion_tokens=3),choices=[NS(finish_reason='stop',message=NS(content=content))])
  def validate(value):
   if not value['accepted']:raise ValueError('required content missing')
  with patch.object(gateway.client.chat.completions,'create',side_effect=structured_response):
   assert gateway.json('structured task',validate)['accepted']
   assert structured==chain[:2]
  gateway.client.close()
print('PASS: local generation/vision fallback order, stable image payload, billed invalid output, unknown failed usage, distinct attempt IDs, successful-model reuse, fail-closed billing; no external calls.')
