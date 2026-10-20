"""Fair single-consumer scheduling, encrypted recovery, admin edits and expiry."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'web')]
from production_queue import ProductionQueue
from storage_lifecycle import UserStorage,TTL,user_directory
from video_project import write_json


def until(predicate,timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.02)
    raise AssertionError('Condition timed out')


with tempfile.TemporaryDirectory(prefix='queue-storage-',dir=ROOT/'.tmp') as tmp:
    root=Path(tmp);resources={'ready':False};events=[];started=[];gate=threading.Event();mutex=threading.Lock();concurrency=[0,0]
    def work(identity,owner,secret):
        assert secret=={'api_key':'private-test-model-key'}
        with mutex:concurrency[0]+=1;concurrency[1]=max(concurrency);started.append(identity)
        if identity=='c1':assert gate.wait(8)
        time.sleep(.03)
        with mutex:concurrency[0]-=1
    def describe(operation,args):return {'owner':args[1],'title':args[0],'kind':'video','stage':'outline','estimate':[1,3]}
    def state(row,value):events.append((row['identity'],value))
    key=os.urandom(32);secret={'api_key':'private-test-model-key'}
    q=ProductionQueue(root/'queue','prod',key,{'video':work},{},describe,state,lambda:resources.copy(),interval=.02);q.start()
    try:
        for identity,owner in [('a1','a'),('a2','a'),('a3','a'),('b1','b'),('c1','c')]:q.submit(work,identity,owner,secret)
        snapshot=q.admin_snapshot();assert [r['identity'] for r in snapshot['waiting']]==['a1','b1','c1','a2','a3']
        assert not started and q.snapshot('a1')['waiting_for']=='memory'
        assert q.snapshot('a1')['wait_minutes'] is None
        with q.connection() as db:
            payload=db.execute('SELECT payload FROM tasks LIMIT 1').fetchone()[0]
            assert b'private-test-model-key' not in payload and not payload.startswith(b'[')
        rows={r['identity']:r['seq'] for r in snapshot['waiting']}
        q.cancel(rows['a2'],'admin')
        try:q.cancel(rows['b1'],'a',owner='a')
        except HTTPException as error:assert error.status_code==404
        else:raise AssertionError('cross-account cancellation accepted')
        try:q.reorder([rows['c1']],snapshot['version'],'admin')
        except HTTPException as error:assert error.status_code==409
        else:raise AssertionError('stale reorder accepted')
        snap=q.admin_snapshot();order=[rows['c1'],rows['a1'],rows['b1'],rows['a3']]
        q.reorder(order,snap['version'],'admin');assert q.admin_snapshot()['waiting'][0]['identity']=='c1'
        resources['ready']=True;until(lambda:started==['c1'])
        try:q.cancel(rows['c1'],'admin')
        except HTTPException as error:assert error.status_code==409
        else:raise AssertionError('running job removed')
        q.progress('c1','render');assert q.snapshot('a1')['active_stage']=='render'
        snap=q.admin_snapshot();q.reorder([],snap['version'],'admin')
        q2=ProductionQueue(root/'queue','preview',os.urandom(32),{'video':work},{},describe,state,lambda:resources.copy(),interval=.02);q2.start()
        q2.submit(work,'d1','d',secret);time.sleep(.1);assert started==['c1'],'second worker ran concurrently'
        gate.set();until(lambda:len(started)==5 and concurrency[0]==0)
        assert started.index('b1')<started.index('a3') and started.index('d1')<started.index('a3'),started
        assert concurrency[1]==1,concurrency
        q2.shutdown(wait=True)
        with q.connection() as db:assert db.execute('SELECT count(*) FROM tasks WHERE payload IS NOT NULL').fetchone()[0]==0
        resources['ready']=False;q.submit(work,'recovered','r',secret)
    finally:q.shutdown(wait=True)
    restored=ProductionQueue(root/'queue','prod',key,{'video':work},{},describe,state,lambda:resources.copy(),interval=.02);restored.start()
    resources['ready']=True;until(lambda:'recovered' in started);restored.shutdown(wait=True)

    projects=root/'projects';private=root/'private';public=root/'web/public/showcase';public.mkdir(parents=True);(public/'example.mp4').write_bytes(b'permanent example')
    pinned=projects/'sample';pinned.mkdir(parents=True)
    write_json(root/'deliverables/manifest.json',{'videos':[{'project':'projects/sample'}]})
    storage=UserStorage(root,projects,private);jobs={}
    for identity,status in [('expired','complete'),('running','running'),('waiting','queued'),('sample','complete')]:
        project=pinned if identity=='sample' else user_directory(projects,'studio',identity,'a'*32)
        project.mkdir(parents=True,exist_ok=True);(project/'video.mp4').write_bytes(b'user video')
        record={'id':identity,'owner_id':'a'*32,'prompt':identity,'project':str(project),'status':status,'expires_at':time.time()-1}
        write_json(project/'studio_job.json',record);jobs[identity]=record
    removed=storage.collect(jobs,{})
    assert removed==['expired'] and jobs['expired']['status']=='expired'
    assert not list(projects.glob('users/*/*-studio-expired/video.mp4'))
    assert all(Path(jobs[k]['project']).exists() for k in ['running','waiting','sample'])
    assert (public/'example.mp4').read_bytes()==b'permanent example'
    assert storage.expired_records('video')[0]['id']=='expired'
    storage.stamp(jobs['running'],'running') # Still running does not reset expiry.
    jobs['running']['status']='complete';storage.stamp(jobs['running'],'running')
    assert TTL-2<jobs['running']['expires_at']-time.time()<=TTL
    legacy=projects/'studio-legacy';legacy.mkdir();write_json(legacy/'studio_job.json',{'id':'legacy','status':'complete','owner_id':'a'*32})
    storage.migrate();assert json.loads((legacy/'studio_job.json').read_text())['expires_at']>time.time()+TTL-2
    # Original inputs must survive while a queued revision is waiting for them.
    jobs['running'].update(status='complete',expires_at=time.time()-1)
    jobs['waiting']['revision_parent']='running'
    assert 'running' not in storage.collect(jobs,{})
    assert Path(jobs['running']['project']).is_dir()
    orphan=user_directory(projects,'studio','abandoned-upload','a'*32);orphan.mkdir(parents=True)
    (orphan/'upload.bin').write_bytes(b'abandoned upload');past=time.time()-TTL-5;os.utime(orphan,(past,past))
    fresh=user_directory(projects,'studio','current-upload','a'*32);fresh.mkdir(parents=True)
    storage.collect(jobs,{})
    assert not orphan.exists() and fresh.is_dir()
print('PASS: fair A/B/C turns, global one consumer across environments, memory waiting, admin reorder/cancel/stale protection, encrypted restart recovery, secrets removed on completion, expiry cleanup, active protection, permanent samples and legacy grace.')
