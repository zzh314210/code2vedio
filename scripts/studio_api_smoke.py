"""Multi-tenant worker boundaries and uploads without paid network requests."""
import importlib.util,sys,tempfile,threading,os,json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from worker_test_support import WorkerClient
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('studio_api_test',ROOT/'web/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
server.jobs={};called=threading.Event();captured={}
def fake_worker(identity,project,prompt,config,materials,*args):
    captured.update(identity=identity,project=project,prompt=prompt,materials=materials,config=config)
    called.set()
with tempfile.TemporaryDirectory() as tmp:
    private=Path(tmp)/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32))
    with patch.object(server,'STUDIO_PROJECTS',Path(tmp)/'projects'),patch.object(server,'PRIVATE',private),patch.object(server,'work',fake_worker):
        client=WorkerClient(server);other=WorkerClient(server,user='b'*32)
        assert TestClient(server.app).get('/api/jobs').status_code==403
        response=client.post('/api/jobs',data={'prompt':'根据上传的材料生成教学视频','style':'studio_editorial','duration':'30'},files=[('files',('../source.md',b'# verified material','text/markdown'))])
        assert response.status_code==202,response.text
        assert called.wait(5)
        identity=response.json()['id'];target=captured['materials'][0]
        assert target.resolve().is_relative_to(Path(tmp).resolve())
        record=(captured['project']/'studio_job.json').read_text()
        assert 'test-generation-secret' not in record and 'test-review-secret' not in record
        assert len(client.get('/api/jobs').json())==1
        assert other.get('/api/jobs').json()==[]
        for suffix in ('','/video','/poster','/report','/planning','/usage','/subtitles'):
            assert other.get('/api/jobs/'+identity+suffix).status_code==404,suffix
        for suffix in ('/retry','/planning/outline/revise','/planning/outline/approve'):
            assert other.post('/api/jobs/'+identity+suffix,json={}).status_code==404,suffix
        assert other.put('/api/jobs/'+identity+'/planning/outline',json={}).status_code==404
        assert other.patch('/api/jobs/'+identity+'/planning-mode',json={}).status_code==404
        assert captured['config']['text']['api_key']=='test-generation-secret'
        assert captured['config']['text']['model']=='test-model'
        assert '/'+('a'*32)+'/' in captured['config']['teaching_research']['library']
        from teaching_library import TeachingLibrary
        lib=TeachingLibrary(captured['config']['teaching_research']['library'])
        source=lib.put({'url':'https://example.com/a','title':'私有参考','text':'私有参考正文内容。'*30})
        assert client.get('/api/sources/'+source['id']).status_code==200
        assert other.get('/api/sources/'+source['id']).status_code==404
        assert other.get('/api/sources').json()['results']==[]
        server.jobs={};server.discover()
        assert client.get('/api/jobs/'+identity).status_code==200
        assert other.get('/api/jobs/'+identity).status_code==404
server.executor.shutdown(wait=True)
print('PASS: signed worker boundary, multipart upload, private configs, job/subresource isolation, private source library and restart ownership.')
