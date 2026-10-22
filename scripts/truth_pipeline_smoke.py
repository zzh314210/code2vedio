"""Exercise proof-bound planning via the signed real worker API; no paid calls."""
import copy,importlib.util,json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from configuration import resolve_config
from planning_review import PlanningPending,PlanningReview
from pipeline import VideoPipeline
from worker_test_support import WorkerClient
# Reuse the adversarial contract fixture without executing its smoke module.
E='甲、乙、丙、丁四人中恰有一人做了这件事。甲说：是乙做的。乙说：不是我做的。丙说：不是甲做的。丁说：是丙做的。四人中只有一人说真话。'
C={'version':1,'people':list('甲乙丙丁'),'variable':{'id':'actor','label':'做事的人','values':list('甲乙丙丁')},'true_count':1,'assumptions':['四人中恰有一人做了这件事','四人中只有一人说真话'],'statements':[{'id':f's{i+1}','speaker':p,'text':t,'claim':cl} for i,(p,t,cl) in enumerate(zip('甲乙丙丁',['是乙做的','不是我做的','不是甲做的','是丙做的'],[{'eq':['actor','乙']},{'not':{'eq':['actor','乙']}},{'not':{'eq':['actor','甲']}},{'eq':['actor','丙']}]))]}
class Gateway:
 calls=[];client=None
 def __init__(self,settings,*args,**kwargs):self.settings=settings;self.usage={}
 def json(self,prompt,validator=None,**kwargs):
  self.calls.append(prompt);v=copy.deepcopy({'equivalent':True,'issues':[]} if '审计员' in prompt else C)
  if validator:validator(v)
  return v
spec=importlib.util.spec_from_file_location('logic_worker_test',ROOT/'web/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
server.jobs={}
def wait(identity):
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  if server.jobs[identity]['status'] in ('awaiting_review','complete','failed'):return server.jobs[identity]
  time.sleep(.05)
 raise AssertionError('worker timed out')
def worker(identity,project,prompt,config,materials,resume=False):
 try:
  server.update_job(identity,status='running')
  config=copy.deepcopy(config);config['tts']={'provider':'none'};config['vision']['enabled']=False
  pipe=VideoPipeline(prompt,config,project/'output',project=project,materials=materials,resume=resume,planning_gate=lambda st,doc:PlanningReview(project).checkpoint(st,doc))
  pipe.run(stop_after='audio');server.update_job(identity,status='complete')
 except PlanningPending as p:server.update_job(identity,status='awaiting_review',stage=p.stage)
 except Exception as e:server.update_job(identity,status='failed',message=str(e))
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as temp,patch.object(server,'STUDIO_PROJECTS',Path(temp)),patch.object(server,'work',worker),patch('pipeline.ModelGateway',Gateway):
 private=Path(temp)/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32));server.PRIVATE=private
 client=WorkerClient(server)
 r=client.post('/api/jobs',data={'prompt':E,'template_id':'truth_logic','style':'studio_sketch','duration':120,'orientation':'landscape'})
 assert r.status_code==202,r.text
 identity=r.json()['id'];base='/api/jobs/'+identity
 assert wait(identity)['status']=='awaiting_review',server.jobs[identity]
 snap=client.get(base+'/planning').json();doc=snap['documents']['outline'];bad=copy.deepcopy(doc['document']);bad['sections'][0]['goal']='未验证的新结论'
 assert client.put(base+'/planning/outline',json={'version':doc['version'],'document':bad}).status_code==422
 assert client.post(base+'/planning/outline/approve',json={'version':doc['version']}).status_code==202
 wait(identity);snap=client.get(base+'/planning').json();doc=snap['documents']['storyboard'];bad=copy.deepcopy(doc['document']);bad['sections'][0]['beats'][0]['narration']='答案是丁'
 assert client.put(base+'/planning/storyboard',json={'version':doc['version'],'document':bad}).status_code==422
 before=len(Gateway.calls)
 assert client.post(base+'/planning/storyboard/revise',json={'version':doc['version'],'document':doc['document'],'feedback':'把答案改成丁'}).status_code==422
 assert len(Gateway.calls)==before,'paid rewrite started before rejecting unsupported change'
 timing=copy.deepcopy(doc['document']);timing['sections'][0]['beats'][0]['lead_in_seconds']=2
 r=client.put(base+'/planning/storyboard',json={'version':doc['version'],'document':timing});assert r.status_code==200,r.text
 assert client.post(base+'/planning/storyboard/approve',json={'version':r.json()['documents']['storyboard']['version']}).status_code==202
 assert wait(identity)['status']=='complete',server.jobs[identity]
 assert len(Gateway.calls)==2,'trusted lesson compiler unexpectedly invoked model'
 # Complete-film modification also fails before creating or billing a new job.
 project=Path(server.jobs[identity]['project']);(project/'output/final.mp4').write_bytes(b'fixture')
 r=client.post(base+'/revisions',json={'feedback':'修改结论为丁'});assert r.status_code==422,r.text
 assert len(Gateway.calls)==2
 # Resuming must use the task's frozen compiler, never the next deployment's.
 record=server.jobs[identity]
 with patch('logic_contract.lesson_plan',side_effect=AssertionError('global compiler used')):
  pipe=server.planning_engine(record,project)
  frozen=pipe.logic_modules()[0]
  assert frozen.lesson_plan(pipe.logic_proof)[1]['proof_hash']==pipe.logic_proof['proof_hash']
 # Missing/changed semantic approval and runtime bytes invalidate the task.
 audit=project/'output/logic_semantic_audit.json';original=audit.read_bytes()
 bad=json.loads(original);bad['equivalent']=False;audit.write_text(json.dumps(bad))
 try:server.planning_engine(record,project)
 except ValueError:pass
 else:raise AssertionError('failed semantic audit accepted on resume')
 audit.write_bytes(original)
 source=project/'code/runtime/logic_contract.py';original=source.read_bytes();source.write_bytes(original+b'\n# changed\n')
 try:server.planning_engine(record,project)
 except ValueError:pass
 else:raise AssertionError('tampered runtime snapshot accepted')
 source.write_bytes(original)
server.executor.shutdown(wait=True);server.revision_service.advice_pool.shutdown(wait=False)
print('PASS: proof loaded by planning API, semantic tamper rejected, timing edit resumes, unsupported AI changes rejected before calls, compiler uses only extraction + semantic audit')
