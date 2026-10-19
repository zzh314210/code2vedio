"""Finished-film revision ownership, frozen inputs, review gates and opt-in AI."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'web'),str(ROOT/'scripts')]
from worker_test_support import WorkerClient
from video_project import write_json
from configuration import merge
from user_config import runtime_config
from pipeline import VideoPipeline
from planning_review import PlanningReview,PlanningPending
import revision_api

spec=importlib.util.spec_from_file_location('server_revision_test',ROOT/'web/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

outline={'topic':'平均变化率','target_audience':'初学者','warnings':[],'sections':[{'id':'section_1','title':'看见变化','goal':'理解变化','key_points':['两点之间的变化'],'sources':[]}]}
story={'sections':[{'id':'section_1','title':'看见变化','beats':[{'narration':'两点之间的变化，看的是平均变化率。','caption':'平均变化率','visual':'点沿曲线接近，连线跟着转动。'}]}]}
quotes=['先确定两个观察位置，比较两个点的函数值。','再计算自变量的变化，避免把间隔直接取成零。','将函数值变化量除以自变量变化量，得到平均变化率。']
source_text=''.join(quotes)
research={'sources':[{'id':'WEB1','text':source_text,'sha256':hashlib.sha256(source_text.encode()).hexdigest(),'title':'原作者的完整解说','url':'https://example.org/original'}],
          'plan':{'primary_source_id':'WEB1','selection_reason':'完整原文','learner_start':'理解两个点','method':'观察再计算','applicability':'间隔非零','pitfalls':['不可除以零'],
                  'steps':[{'id':f'T{i+1}','source_id':'WEB1','quote':quote,'explanation':quote,'why':'按定义比较变化','student_question':'为什么比较两点','visual_action':'展示两点与割线'} for i,quote in enumerate(quotes)]}}
outline['sections'][0].update(sources=['WEB1'],teaching_steps=['T1','T2','T3'])
story['sections'][0]['beats'][0].update(teaching_step_ids=['T1','T2','T3'],student_question='两点如何比较变化？',reasoning='函数值变化除以非零的自变量变化。')
suggestion={'summary':'可以让变化过程更清楚。','suggestions':[{'title':'先动点，再解释','reason':'先看运动有助于理解。','feedback':'先展示动点与连线变化，再解释平均变化率。'}]}

class Gateway:
    calls=[]
    client=None
    def __init__(self,settings,role='text',**kwargs):self.settings=settings;self.role=role
    def json(self,prompt,validator,**kwargs):
        self.calls.append((self.role,prompt,self.settings))
        result=copy.deepcopy(suggestion if self.role=='vision' else {'summary':'第二幕先展示动点，再出现文字。','duration':30,'outline':outline,'storyboard':story})
        if self.role=='text':result['storyboard']['sections'][0]['beats'][0]['visual']='先展示动点和跟随旋转的连线，再显示平均变化率标签。'
        validator(result);return result

with tempfile.TemporaryDirectory(prefix='revision-api-',dir=ROOT/'.tmp') as directory:
    base=Path(directory);private=base/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32))
    projects=base/'projects';parent=projects/'studio-parent';parent.mkdir(parents=True)
    with patch.object(server,'PRIVATE',private),patch.object(server,'STUDIO_PROJECTS',projects),patch.object(server,'jobs',{}),patch.object(server.editing_service,'jobs',{}),patch.object(server.executor,'submit') as submit,patch.object(server.revision_service.advice_pool,'submit') as advice_submit,patch.object(revision_api,'ModelGateway',Gateway),patch.object(revision_api,'validate_public_endpoint'),patch.object(revision_api,'sample_frames',return_value=[]),patch.object(revision_api,'probe',return_value={'duration':30}):
        client=WorkerClient(server)
        config=runtime_config(server.settings,client.personal,private/'library.sqlite3')
        config=merge(config,{'style':'studio_editorial','video':{'target_duration':30,'max_sections':1,'max_beats':6},'teaching_research':{'enabled':False}})
        pipe=VideoPipeline('制作平均变化率的教程',config,parent/'output',project=parent)
        write_json(parent/'output/outline.json',outline);write_json(parent/'output/storyboard.json',story);(parent/'output/final.mp4').write_bytes(b'preserved-original-film')
        write_json(parent/'output/teaching_research/research.json',research)
        (parent/'input/materials/original-note.txt').write_text('这是原作者上传的笔记，不能被其他用户读取或原地覆盖。')
        server.jobs['parent']={'id':'parent','owner_id':client.user,'project':str(parent),'status':'complete','stage':'compose','prompt':'制作平均变化率的教程','style':'studio_editorial','duration':30}
        def hashes():return {str(p.relative_to(parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.rglob('*') if p.is_file() and p.name!='.project.lock'}
        original=hashes()
        foreign=WorkerClient(server,user='b'*32)
        for path in ['/api/jobs/parent/revision-advice','/api/jobs/parent/revisions']:
            response=foreign.post(path,json={'feedback':'换一个例子'});assert response.status_code==404,response.text
        assert client.get('/api/jobs/parent/revision-advice').json()['status']=='idle' and not Gateway.calls
        response=client.post('/api/jobs/parent/revisions',json={'feedback':'  '});assert response.status_code==422
        payload={'feedback':'第二幕先用动点解释，再出现文字。','request_id':'test-revision-request-001'}
        response=client.post('/api/jobs/parent/revisions',json=payload);assert response.status_code==202,response.text
        identity=response.json()['id'];assert identity!='parent' and submit.call_count==1
        again=client.post('/api/jobs/parent/revisions',json=payload);assert again.status_code==202 and again.json()['id']==identity and submit.call_count==1
        blocked=client.post('/api/jobs/parent/revisions',json={**payload,'request_id':'test-revision-request-002'});assert blocked.status_code==409
        assert hashes()==original

        def resume_to_gate(identity,project,prompt,runtime,materials,resume):
            child_pipe=VideoPipeline(prompt,runtime,project/'output',project=project,resume=resume,planning_gate=lambda stage,document:PlanningReview(project).checkpoint(stage,document))
            try:child_pipe.run(stop_after='storyboard')
            except PlanningPending as pending:server.update_job(identity,status='awaiting_review',stage=pending.stage)
            else:raise AssertionError('Revision must wait for requested manual review')
        function,*args=submit.call_args.args
        with patch.object(server,'work',resume_to_gate):function(*args)
        record=server.jobs[identity];assert record['status']=='awaiting_review',record.get('message')
        assert record['revision_parent']=='parent' and record['revision_number']==2 and record['revision_prepared']
        child=Path(record['project']);assert (child/'input/materials/original-note.txt').is_file()
        snapshot=PlanningReview(child).snapshot();assert snapshot['pending_stage']=='storyboard'
        assert snapshot['documents']['outline']['approved'] and not snapshot['documents']['storyboard']['approved']
        assert snapshot['documents']['storyboard']['document']['sections'][0]['beats'][0]['visual'].startswith('先展示动点')
        assert json.loads((child/'output/teaching_research/research.json').read_text())==research
        assert 'teaching_step_ids' in Gateway.calls[-1][1] and 'T3' in Gateway.calls[-1][1]
        assert hashes()==original,'Revision changed original project'
        assert Gateway.calls[-1][2]['billing_context']['job_id']==identity
        response=client.get('/api/jobs/'+identity);assert response.status_code==200 and 'project' not in response.json()

        # A transient planning failure must be retryable without corrupting the
        # partially copied project or touching the completed original.
        response=client.post('/api/jobs/parent/revisions',json={**payload,'request_id':'test-revision-request-retry'})
        failed=response.json()['id'];function,*args=submit.call_args.args
        with patch.object(Gateway,'json',side_effect=RuntimeError('Temporary planning outage')):function(*args)
        assert server.jobs[failed]['status']=='failed' and not server.jobs[failed]['revision_prepared']
        response=client.post('/api/jobs/'+failed+'/retry');assert response.status_code==202,response.text
        function,*args=submit.call_args.args
        with patch.object(server,'work',resume_to_gate):function(*args)
        assert server.jobs[failed]['status']=='awaiting_review',server.jobs[failed].get('message')
        assert hashes()==original

        response=client.post('/api/jobs/parent/revision-advice',json={});assert response.status_code==202 and advice_submit.call_count==1
        response=client.post('/api/jobs/parent/revision-advice',json={});assert response.status_code==202 and advice_submit.call_count==1
        assert len(Gateway.calls)==2,'AI ran before submitted worker executes'
        function,*args=advice_submit.call_args.args;function(*args)
        state=client.get('/api/jobs/parent/revision-advice').json();assert state['status']=='ready' and state['suggestions'][0]['feedback']==suggestion['suggestions'][0]['feedback']
        assert Gateway.calls[-1][0]=='vision'
        assert (parent/'output/final.mp4').read_bytes()==b'preserved-original-film'
        assert server.jobs['parent']['status']=='complete'
    pipe.text.client.close();pipe.vision.client.close()
server.executor.shutdown(wait=False);server.revision_service.advice_pool.shutdown(wait=False)
print('PASS: ownership, opt-in advice, duplicate suppression, immutable original, copied materials and verified evidence/step IDs, valid resume fingerprint, separate version, changed storyboard, manual approval, usage attribution')
