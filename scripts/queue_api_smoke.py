"""Exercise the real signed worker with the durable queue enabled; no paid models."""
import importlib.util,json,os,sys,tempfile,threading,time
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'web'),str(ROOT/'scripts')]
from worker_test_support import WorkerClient

def until(fn):
 deadline=time.monotonic()+10
 while time.monotonic()<deadline:
  if fn():return
  time.sleep(.05)
 raise AssertionError('timed out')

with tempfile.TemporaryDirectory(prefix='queue-api-',dir=ROOT/'.tmp') as tmp:
 base=Path(tmp);private=base/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32))
 os.environ.update(C2V_ACCOUNT_DIR=str(private),C2V_PROJECT_DIR=str(base/'projects'),C2V_QUEUE_ENABLED='1',C2V_QUEUE_DIR=str(base/'queue'),C2V_QUEUE_NAMESPACE='test',C2V_QUEUE_MIN_AVAILABLE_MB='0')
 def boot(name):
  spec=importlib.util.spec_from_file_location(name,ROOT/'web/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server);return server
 server=boot('queue_server_1');begun=[];block=threading.Event()
 def work(identity,project,prompt,config,materials,*args):
  assert config['text']['api_key']=='test-generation-secret'
  begun.append(identity)
  if len(begun)==1:assert block.wait(15)
  server.update_job(identity,status='complete',stage='compose')
 server.work=work
 with WorkerClient(server) as a:
  b=WorkerClient(server,user='b'*32);admin=WorkerClient(server,user='c'*32,role='admin')
  def create(client,prompt):
   response=client.post('/api/jobs',data={'prompt':prompt,'style':'studio_noir','duration':30,'auto_approve':'true'});assert response.status_code==202,response.text;return response.json()['id']
  first=create(a,'用户甲的第一个视频');until(lambda:begun==[first])
  second=create(a,'用户甲的第二个视频');third=create(b,'用户乙的第一个视频')
  state=b.get('/api/jobs/'+third).json();assert state['status']=='queued' and state['queue']['ahead']==1,state
  assert 'project' not in state and 'owner_id' not in state
  assert a.get('/api/jobs/'+third).status_code==404
  assert a.get('/api/admin/queue').status_code==403
  snapshot=admin.get('/api/admin/queue').json();assert [j['identity'] for j in snapshot['waiting']]==[third,second],snapshot
  version=snapshot['version'];order=[j['seq'] for j in reversed(snapshot['waiting'])]
  response=admin.put('/api/admin/queue/order',json={'order':order,'version':version});assert response.status_code==200,response.text
  response=b.post('/api/jobs/'+second+'/cancel');assert response.status_code==404
  cancel_id=next(t['seq'] for t in snapshot['waiting'] if t['identity']==third)
  assert admin.delete('/api/admin/queue/'+str(cancel_id)).status_code==200
  assert b.get('/api/jobs/'+third).json()['status']=='cancelled'
  assert a.post('/api/jobs/'+first+'/cancel').status_code==409
  block.set();until(lambda:a.get('/api/jobs/'+second).json()['status']=='complete')
  assert begun==[first,second]
  assert a.get('/api/jobs/'+second).json()['expires_at']>time.time()+86390
  # Persist a pending task and close the worker while the resource gate holds.
  server.production_queue.resources=lambda:{'ready':False}
  pending=create(a,'重启后仍然等待的视频');assert a.get('/api/jobs/'+pending).json()['queue']['waiting_for']=='memory'
  extra=[create(a,'满额测试中的等待视频 '+str(i)) for i in range(4)]
  rejected=a.post('/api/jobs',data={'prompt':'不能超过每个用户队列上限','style':'studio_noir','duration':30})
  assert rejected.status_code==429
  assert a.post('/api/jobs/'+third+'/retry').status_code==404
  # Simulate filling the queue between the preflight and durable admission.
  with patch.object(server.production_queue,'ensure_capacity',return_value=None):
   rejected=a.post('/api/jobs',data={'prompt':'上传期间队列满额的测试视频','style':'studio_noir','duration':30})
   assert rejected.status_code==429,rejected.text
  failed=next(j for j in a.get('/api/jobs').json() if j['prompt']=='上传期间队列满额的测试视频')
  assert failed['status']=='failed' and not server.production_queue.has_pending(failed['id'])
  assert a.post('/api/jobs/'+failed['id']+'/retry').status_code==429
  assert a.get('/api/jobs/'+failed['id']).json()['status']=='failed'
  for identity in extra:assert a.post('/api/jobs/'+identity+'/cancel').status_code==200
  b.close();admin.close()
 server2=boot('queue_server_2');resumed=[]
 def resumed_work(identity,project,prompt,config,materials,*args):
  assert config['text']['api_key']=='test-generation-secret';resumed.append(identity);server2.update_job(identity,status='complete',stage='compose')
 server2.work=resumed_work
 with WorkerClient(server2) as client:
  until(lambda:client.get('/api/jobs/'+pending).json()['status']=='complete')
  assert resumed==[pending]
  assert client.get('/api/jobs/'+first).json()['status']=='complete'
print('PASS: real signed queue admission, user isolation, admin authorization/reordering/cancellation, queued-state polling, timestamped storage, expiry metadata and encrypted restart recovery; no model calls.')
