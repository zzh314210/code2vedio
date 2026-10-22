"""Every upstream attempt is bounded, including fallback and JSON format repairs."""
import sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from model_gateway import ModelGateway
from quality_harness import QualityBudget,QualityBudgetExceeded
from configuration import merge,DEFAULTS

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as td:
 settings=merge(DEFAULTS['text'],{'protocol':'chat_completions','base_url':'https://example.org/v1','api_key':'fixture','model':'primary','fallback_models':['backup'],'max_retries':0,'usage_stage':'code'})
 g=ModelGateway(settings);g.budget=QualityBudget(Path(td)/'fallback',{'max_model_calls':1})
 attempts=[]
 def failed_request(self,prompt,images=None,max_tokens=None):
  # This controlled transport keeps the exact gateway admission placement.
  self.budget.take_call(self.role,'code',self.settings['model']);attempts.append(self.settings['model']);raise RuntimeError('upstream unavailable')
 g._request=types.MethodType(failed_request,g)
 try:g.request('test')
 except QualityBudgetExceeded:pass
 else:raise AssertionError('fallback exceeded total cap')
 assert attempts==['primary'] and len(g.budget.state['calls'])==1
 g.client.close()
 # The configured JSON correction limit applies to code created during review too.
 for stage in ('code','render','review','acceptance'):
  c={**settings,'usage_stage':stage};gateway=ModelGateway(c);gateway.budget=QualityBudget(Path(td)/stage,{'code_revisions':0,'visual_revisions':5})
  requested=[]
  def invalid(prompt,**kw):requested.append(prompt);return 'invalid-json',{}
  gateway.request=invalid
  try:gateway.json('repair')
  except ValueError:pass
  else:raise AssertionError('invalid code accepted')
  assert len(requested)==1,(stage,'code correction limit bypassed')
  gateway.client.close()
print('PASS: fallback cannot bypass durable total cap; zero code revisions prevents JSON repair retries in generation/render/review/final stages')
