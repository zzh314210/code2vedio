"""Multipart upload boundary test, isolated from live jobs and all external APIs."""
import importlib.util,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('studio_api_test',ROOT/'web/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
server.settings['text']['api_key']='test-generation-secret'
server.settings['vision']['api_key']='test-review-secret'
server.jobs={};called=threading.Event();captured={}
def fake_worker(identity,project,prompt,config,materials,*args):
    captured.update(identity=identity,project=project,prompt=prompt,materials=materials,config=config)
    called.set()
with tempfile.TemporaryDirectory() as tmp,patch.object(server,'STUDIO_PROJECTS',Path(tmp)),patch.object(server,'work',fake_worker):
    client=TestClient(server.app)
    r=client.post('/api/jobs',data={'prompt':'根据上传的材料生成教学视频','style':'studio_editorial','duration':'30','orientation':'landscape'},files=[('files',('../source.md',b'# verified material\nSample geometry lesson.','text/markdown'))])
    assert r.status_code==202,r.text
    assert called.wait(5)
    assert len(captured['materials'])==1
    target=captured['materials'][0]
    assert target.resolve().is_relative_to(Path(tmp).resolve()) and target.read_bytes().startswith(b'# verified')
    record=(captured['project']/'studio_job.json').read_text(encoding='utf8')
    assert 'test-generation-secret' not in record and 'test-review-secret' not in record
    assert client.post('/api/jobs',data={'prompt':'短','style':'invalid'}).status_code==400
    assert client.post('/api/config',headers={'Origin':'https://foreign.example'},json={}).status_code==403
    from copy import deepcopy
    original_cloud=deepcopy(server.cloud_tts)
    with patch.object(server,'cloud_tts',{'provider':'qwen_audio','model':'test-cloud-tts','base_url':'https://example.org/v1'}),patch.object(server,'local_speech',{'provider':'gpt_sovits','url':'http://127.0.0.1:9880/tts','ref_audio_path':'test.wav','prompt_text':'test'}):
        local=client.post('/api/config',json={'tts_provider':'gpt_sovits'})
        assert local.status_code==200 and local.json()['tts_provider']=='gpt_sovits'
        cloud=client.post('/api/config',json={'tts_provider':'qwen_audio'})
        assert cloud.status_code==200 and server.settings['tts']['api_key']=='test-generation-secret'
        assert 'test-generation-secret' not in cloud.text
        with patch.object(server,'local_speech',{}):
            assert client.post('/api/config',json={'tts_provider':'gpt_sovits'}).status_code==400
    server.settings['tts']=original_cloud
    sample=client.get('/api/speech/sample')
    if (ROOT/'deliverables/speech/male_teacher_cpu.wav').is_file():assert sample.status_code==200 and sample.content[:4]==b'RIFF'

    server.jobs={};called.clear()
    prompt='制作30秒六面体公共边视频，使用我描述的新例题，不使用内置演示题。'
    response=client.post('/api/jobs',data={'prompt':prompt,'style':'studio_sketch','duration':'30','orientation':'landscape'})
    assert response.status_code==202,response.text
    assert called.wait(5)
    assert captured['prompt']==prompt and captured['materials']==[]
    assert captured['config'].get('task',{}).get('component_profile')!='cube_baseline'
server.executor.shutdown(wait=True)
print('PASS: multipart material archived and passed to pipeline, path contained, job metadata excludes keys, invalid input rejected, foreign-origin writes blocked; topic keywords do not inject baseline tasks/material; no external API calls.')
