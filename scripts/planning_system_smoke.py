"""Exercise real pipeline gates and Studio editing APIs without billed remote calls."""
import copy
import importlib.util
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from configuration import resolve_config
from pipeline import VideoPipeline
from planning_review import PlanningPending,PlanningReview,version_of
from model_gateway import ModelGateway
from teaching_research import validate_plan,validate_step_coverage
from teaching_library import TeachingLibrary,parse_captions

OUTLINE={'topic':'变化的含义','target_audience':'初学者','warnings':[],'sections':[{'id':'section_1','title':'先观察变化','goal':'理解增减','key_points':['先观察再计算'],'sources':[]}]}
STORY={'sections':[{'id':'section_1','title':'先观察变化','beats':[{'narration':'先看水位怎样变化，再比较流入和流出。','caption':'观察水位变化','visual':'水池水位随入水和出水逐步变化。','duration_seconds':8,'lead_in_seconds':2}]}]}
class Gateway:
 def __init__(self,settings,*args,**kwargs):self.settings=settings;self.usage={};self.client=None
 def json(self,prompt,validator=None,*args,**kwargs):
  value=copy.deepcopy(STORY if '阶段: STORYBOARD' in prompt else OUTLINE)
  if '创作者修改意见' in prompt or '修改意见（创作者要求）' in prompt:
   value['sections'][0]['title']='先讲清楚净变化'
  if validator:validator(value)
  return value

def wait_for(predicate):
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  if predicate():return
  time.sleep(.05)
 raise AssertionError('Timed out waiting for task state')

spec=importlib.util.spec_from_file_location('planning_test_server',ROOT/'web/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
server.jobs={}
config=resolve_config({'style':'studio_sketch','text':{'model':'fake','api_key':'fake','base_url':'https://example.com/v1'},'vision':{'enabled':False},'tts':{'provider':'none'},'teaching_research':{'enabled':False}})
server.settings=copy.deepcopy(config);server.settings['vision']['api_key']='fake'
# Same pipeline and callbacks, stopping at audio keeps this test independent of code/renderer.
def worker(identity,project,prompt,config,materials,resume=False):
 try:
  server.update_job(identity,status='running')
  pipe=VideoPipeline(prompt,config,project/'output',project=project,materials=materials,resume=resume,planning_gate=lambda stage,doc:PlanningReview(project).checkpoint(stage,doc))
  pipe.run(stop_after='audio')
  server.update_job(identity,status='complete',message='audio reached')
 except PlanningPending as pending:server.update_job(identity,status='awaiting_review',stage=pending.stage)
 except Exception as e:server.update_job(identity,status='failed',message=str(e));raise

with tempfile.TemporaryDirectory() as temp,patch.object(server,'STUDIO_PROJECTS',Path(temp)),patch.object(server,'work',worker),patch('pipeline.ModelGateway',Gateway):
 client=TestClient(server.app)
 response=client.post('/api/jobs',data={'prompt':'演示水位的变化过程','style':'studio_sketch','duration':30})
 assert response.status_code==202,response.text
 identity=response.json()['id'];base=f'/api/jobs/{identity}';project=Path(server.jobs[identity]['project'])
 wait_for(lambda:server.jobs[identity]['status']=='awaiting_review')
 assert server.jobs[identity]['stage']=='outline'
 assert not (project/'output/storyboard.json').exists()
 assert not list((project/'output').rglob('*.wav'))
 snap=client.get(base+'/planning').json();version=snap['documents']['outline']['version']
 edit=copy.deepcopy(snap['documents']['outline']['document']);edit['sections'][0]['goal']='先理解水位变化的原因'
 saved=client.put(base+'/planning/outline',json={'version':version,'document':edit})
 assert saved.status_code==200,saved.text
 assert server.jobs[identity]['status']=='awaiting_review'
 assert client.put(base+'/planning/outline',json={'version':version,'document':OUTLINE}).status_code==409
 version=saved.json()['documents']['outline']['version']
 response=client.post(base+'/planning/outline/revise',json={'version':version,'document':edit,'feedback':'先讲清楚净变化，不要先抛公式'})
 assert response.status_code==202,response.text
 wait_for(lambda:server.jobs[identity]['status']=='awaiting_review')
 snap=client.get(base+'/planning').json()
 assert snap['documents']['outline']['document']['sections'][0]['title']=='先讲清楚净变化',server.jobs[identity]
 assert not (project/'output/storyboard.json').exists()
 version=snap['documents']['outline']['version']
 assert client.post(base+'/planning/outline/approve',json={'version':version}).status_code==202
 wait_for(lambda:server.jobs[identity]['status']=='awaiting_review' and server.jobs[identity]['stage']=='storyboard')
 assert not list((project/'output').rglob('*.wav'))
 # Restart recovery: re-discover durable job metadata and pending stage.
 server.jobs={};server.discover();assert server.jobs[identity]['status']=='awaiting_review'
 snap=client.get(base+'/planning').json()
 # Editing outline at storyboard review invalidates the unapproved storyboard.
 edited=copy.deepcopy(snap['documents']['outline']['document']);edited['sections'][0]['title']='先观察，再解释'
 response=client.put(base+'/planning/outline',json={'version':snap['documents']['outline']['version'],'document':edited})
 assert response.status_code==200,response.text
 assert not (project/'output/storyboard.json').exists()
 assert response.json()['pending_stage']=='outline'
 # Explicitly opt into automatic approval, then both checkpoints must pass.
 assert client.patch(base+'/planning-mode',json={'auto_approve':True}).status_code==202
 wait_for(lambda:server.jobs[identity]['status'] in ('complete','failed'))
 assert server.jobs[identity]['status']=='complete',server.jobs[identity]
 assert list((project/'output').rglob('*.wav'))
 assert PlanningReview(project).snapshot()['documents']['storyboard']['approved']
 assert list((project/'planning_history').glob('*.json'))
 # New auto-approve task never waits for either planning checkpoint.
 response=client.post('/api/jobs',data={'prompt':'演示另一组水位变化','style':'studio_sketch','duration':30,'auto_approve':'true'})
 second=response.json()['id'];wait_for(lambda:server.jobs[second]['status'] in ('complete','failed'))
 assert server.jobs[second]['status']=='complete',server.jobs[second]

# Fallbacks must preserve images, URL/key and call order for both roles.
for role,models in [('text',['kimi-k3','deepseek-v4-flash-0731','deepseek-v4.1-flash']),('vision',['deepseek-v4.1-flash','qwen3.7-flash','qwen3.8-flash'])]:
 gateway=ModelGateway({'protocol':'chat_completions','model':models[0],'fallback_models':models[1:],'base_url':'https://example.com/v1','api_key':'test-key'},role)
 called=[]
 def request(prompt,images,max_tokens):
  called.append(gateway.settings['model']);assert images==['frame.png'];assert gateway.settings['api_key']=='test-key';assert gateway.settings['base_url']=='https://example.com/v1'
  if len(called)<3:raise TimeoutError('request failed')
  return ('ok',{})
 gateway._request=request
 assert gateway.request('prompt',images=['frame.png'])[0]=='ok'
 assert called==models,called
 gateway.client.close()

with tempfile.TemporaryDirectory() as temp:
 library=TeachingLibrary(Path(temp)/'library.db')
 item={'url':'https://example.com/lesson','title':'牛吃草问题 净变化','text':'比较两次条件，先求每日生长量，再求原有草量。'*30,'segments':[{'start':0,'end':3,'text':'先比较条件'}]}
 first=library.put(item);library.put(item)
 assert library.stats()['sources']==1 and library.search('牛吃草')[0]['id']==first['id']
 assert parse_captions('WEBVTT\n\n00:01.000 --> 00:03.000\n先比较条件\n\n')[0]['start']==1
 try:validate_step_coverage({'sections':[{'teaching_steps':['T2','T1']}]},{'steps':[{'id':'T1'},{'id':'T2'}]},'outline')
 except ValueError:pass
 else:raise AssertionError('Reordered reasoning was accepted')
server.executor.shutdown(wait=True)
print('PASS: two real pipeline gates, manual edits, AI revision, stale-version rejection, restart recovery, upstream invalidation, manual/automatic continuation, model fallback chains with images/auth preserved, SQLite dedup/search and timed subtitles.')
