"""Exercise real audio looping/ducking and signed, isolated BGM API operations."""
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'web'), str(ROOT/'scripts')]
from background_music import mix_background_music, compose_background_music, PROJECT_AUDIO
from media import probe
from video_project import copy_project_inputs, write_json
from worker_test_support import WorkerClient


def wav(path, samples, rate=48000):
    with wave.open(str(path), 'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(rate)
        file.writeframes((samples*32767).astype('<i2').tobytes())


def music_amplitude(samples, begin, end):
    segment=samples[int(begin*48000):int(end*48000)]
    times=np.arange(len(segment))/48000
    return 2*abs(np.mean(segment*np.exp(-2j*np.pi*440*times)))


with tempfile.TemporaryDirectory(prefix='bgm-test-', dir=ROOT/'.tmp') as temporary:
    base=Path(temporary); times=np.arange(48000*8)/48000
    # Low-level voice with a 3s central utterance; music must duck without truncating.
    speech=np.sin(2*np.pi*180*times)*.09*((times>=2)&(times<5))
    wav(base/'voice.wav',speech)
    wav(base/'music.wav',np.sin(2*np.pi*440*np.arange(48000)/48000)*.2)
    mix_background_music(base/'voice.wav',base/'music.wav',base/'mix.wav',8,.3)
    with wave.open(str(base/'mix.wav'),'rb') as file:
        mixed=np.frombuffer(file.readframes(file.getnframes()),dtype='<i2').reshape(-1,2).mean(axis=1)/32768
    assert abs(probe(base/'mix.wav')['duration']-8)<.02
    quiet=music_amplitude(mixed,1,1.8); speaking=music_amplitude(mixed,3,4)
    later=music_amplitude(mixed,6,7)
    assert quiet>.02 and later>quiet*.8,(quiet,later)
    assert speaking<quiet*.65,(quiet,speaking)
    assert np.max(np.abs(mixed))<.96
    assert compose_background_music(base,base/'voice.wav',base,8,{'enabled':False})==base/'voice.wav'
    for bad in (float('nan'),float('inf'),-.1,.6):
        try:mix_background_music(base/'voice.wav',base/'music.wav',base/'bad.wav',8,bad)
        except ValueError:pass
        else:raise AssertionError('invalid volume accepted')

    private=base/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32))
    os.environ['C2V_ACCOUNT_DIR']=str(private);os.environ['C2V_PROJECT_DIR']=str(base/'projects')
    spec=importlib.util.spec_from_file_location('bgm_test_server',ROOT/'web/server.py')
    server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
    a,b=WorkerClient(server),WorkerClient(server,user='b'*32)
    response=a.post('/api/music/uploads',files={'file':('我的音乐.wav',(base/'music.wav').read_bytes(),'audio/wav')})
    assert response.status_code==201,response.text
    track=response.json();identity=track['id']
    assert len(a.get('/api/music/uploads').json())==1 and b.get('/api/music/uploads').json()==[]
    assert a.get(track['audio_url']).status_code==200
    assert a.get(track['audio_url'],headers={'Range':'bytes=0-99'}).status_code==206
    assert b.get(track['audio_url']).status_code==404
    assert b.delete('/api/music/uploads/'+identity).status_code==404
    assert a.post('/api/music/uploads',files={'file':('bad.mp3',b'not audio','audio/mpeg')}).status_code==400
    playlist=b'#EXTM3U\n#EXTINF:3\nhttp://127.0.0.1:9/private\n'
    assert a.post('/api/music/uploads',files={'file':('remote.mp3',playlist,'audio/mpeg')}).status_code==400
    with patch.object(server.executor,'submit') as submit:
        def create(**values):
            return a.post('/api/jobs',data={'prompt':'给测试视频添加背景音乐','style':'studio_noir','duration':'30','bgm_enabled':'true','bgm_upload_id':identity,'bgm_volume':'.2',**values})
        assert create(bgm_track_id='easy-lemon').status_code==400
        assert create(bgm_volume='NaN').status_code in (400,422)
        assert create(bgm_upload_id='../../private').status_code==404
        response=create();assert response.status_code==202,response.text
        job=response.json()['id'];_,_,project,_,config,*_=submit.call_args.args
        original=(project/PROJECT_AUDIO).read_bytes()
        assert config['background_music']['id']==identity and config['background_music']['volume']==.2
        assert len(list((project/'uploads').glob('*')))==0,'Music leaked into general/model materials'
        assert a.delete('/api/music/uploads/'+identity).status_code==200
        assert (project/PROJECT_AUDIO).read_bytes()==original,'Deletion affected frozen task'
        # Retry before the pipeline ever creates its manifest must retain the music.
        server.update_job(job,status='failed')
        response=a.post(f'/api/jobs/{job}/retry');assert response.status_code==202,response.text
        retry_config=submit.call_args.args[4]
        assert retry_config['background_music']['id']==identity
        server.update_job(job,status='failed')
        child=base/'revision';copy_project_inputs(project,child)
        assert (child/PROJECT_AUDIO).read_bytes()==original
        compose_background_music(child,base/'voice.wav',base,8,retry_config['background_music'])
        # Preset defaults and optional music-off produce no private file dependencies.
        response=create(bgm_upload_id='',bgm_track_id='easy-lemon');assert response.status_code==202,response.text
        preset=response.json()['id'];preset_project=Path(server.jobs[preset]['project'])
        assert (preset_project/PROJECT_AUDIO).is_file()
        assert a.get(f'/api/jobs/{preset}').json()['background_music']['credit']
        assert b.get(f'/api/jobs/{preset}').status_code==404
        cfg=submit.call_args.args[4]['background_music'];(preset_project/'output').mkdir()
        compose_background_music(preset_project,base/'voice.wav',preset_project/'output',8,cfg)
        server.update_job(preset,status='complete')
        assert a.get(f'/api/jobs/{preset}/music-credit').status_code==200
        assert b.get(f'/api/jobs/{preset}/music-credit').status_code==404
        response=create(bgm_enabled='false',bgm_upload_id='');assert response.status_code==202,response.text
        assert not submit.call_args.args[4]['background_music']['enabled']
    # Expired personal music is hidden and removed; presets remain permanent.
    expired=a.post('/api/music/uploads',files={'file':('expires.wav',(base/'music.wav').read_bytes(),'audio/wav')})
    assert expired.status_code==201,expired.text
    item=expired.json();folder=private/'music'/a.user/item['id'];metadata=json.loads((folder/'track.json').read_text())
    metadata['expires_at']=0;write_json(folder/'track.json',metadata)
    assert a.get(item['audio_url']).status_code==404
    assert item['id'] not in {t['id'] for t in a.get('/api/music/uploads').json()}
    server.music_service.cleanup();assert not folder.exists()
    assert (ROOT/'web/public/bgm/easy-lemon.m4a').is_file()
    a.close();b.close();server.executor.shutdown(wait=False);server.revision_service.advice_pool.shutdown(wait=False)
print('PASS: real 8s loop from 1s music, ducking, unclipped audio, private upload/preview/ranges/deletion, malformed media, immutable retry/revision, preset/off, owned credits. No model calls.')
