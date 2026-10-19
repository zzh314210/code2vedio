"""Editing upload/ownership/versioning/retired-output boundaries with signed requests."""
import importlib.util,sys,tempfile,os
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from worker_test_support import WorkerClient
from editing import execute
from media import ffmpeg_binary
spec=importlib.util.spec_from_file_location('server_edit_test',ROOT/'web/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);private=root/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32))
 video=root/'fixture.mp4';execute([ffmpeg_binary(),'-v','error','-y','-f','lavfi','-i','color=blue:s=320x180:r=30:d=6','-c:v','libx264','-threads','1',str(video)])
 service=server.editing_service
 with patch.object(server,'PRIVATE',private),patch.object(service,'root',root/'edits'),patch.object(service,'jobs',{}),patch.object(service,'schedule') as schedule:
  a=WorkerClient(server);b=WorkerClient(server,user='b'*32)
  response=a.post('/api/edits',data={'prompt':'保留清楚的场景，剪出重点','target_duration':'5'},files=[('files',('fixture.mp4',video.read_bytes(),'video/mp4'))]);assert response.status_code==202,response.text
  identity=response.json()['id'];assert schedule.call_count==1
  assert b.get('/api/edits').json()==[]
  for path in ['', '/source/s1','/video','/poster','/subtitles','/timeline','/project']:
   assert b.get('/api/edits/'+identity+path).status_code==404,path
  assert a.get('/api/edits/'+identity+'/source/s1').status_code==200
  assert a.get('/api/edits/'+identity+'/video').status_code==404
  assert a.post('/api/edits/'+identity+'/render').status_code==409
  service.update(identity,status='awaiting_review',plan={'clips':[{'source_id':'s1','start':0,'end':5,'effect':'none'}]},version=1)
  plan={'version':0,'clips':[{'source_id':'s1','start':0,'end':5,'effect':'none'}]}
  assert a.put('/api/edits/'+identity+'/plan',json=plan).status_code==409
  plan['version']=1;plan['clips'][0]['end']=90
  assert a.put('/api/edits/'+identity+'/plan',json=plan).status_code==422
  plan['clips'][0]['end']=4
  result=a.put('/api/edits/'+identity+'/plan',json=plan);assert result.status_code==200,result.text
  assert result.json()['version']==2 and result.json()['plan']['duration']==4
  assert b.put('/api/edits/'+identity+'/plan',json=plan).status_code==404
  assert a.post('/api/edits/'+identity+'/render').status_code==202
  assert a.post('/api/edits/'+identity+'/render').status_code==409
server.executor.shutdown(wait=False)
print('PASS: signed editing API, real video upload, owned source streaming, cross-user isolation, version conflicts, range validation, pre-export gating, duplicate export rejection.')
