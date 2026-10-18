"""Local FastAPI studio. Credentials remain in process memory, jobs use the existing pipeline."""
import copy
import mimetypes
import json
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from configuration import load_config, merge, sanitize_error, public_config
from pipeline import VideoPipeline, STAGES
from planning_review import PlanningReview, PlanningPending, ReviewConflict
from teaching_library import TeachingSources
from teaching_research import validate_plan
from execution import project_lock
from media import run_command, ffmpeg_binary, probe
from styles import list_styles
from video_project import safe_name, write_json, restore_credentials

mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

app=FastAPI(title='Code2Video Studio',docs_url=None,redoc_url=None)
lock=threading.RLock()
executor=ThreadPoolExecutor(max_workers=1)
config_file=next((ROOT/name for name in ('config.qwen-tts.local.json','config.local.json','config.studio.example.json') if (ROOT/name).is_file()),None)
settings=load_config(config_file)
settings=merge(settings,{'text':{'model':'kimi-k3','fallback_models':['deepseek-v4-flash-0731','deepseek-v4.1-flash']},'vision':{'fallback_models':['qwen3.7-flash','qwen3.8-flash'],'enabled':True,'inherit_text':False,'frames':12,'rounds':2,'timeout':120,'extra_body':{'enable_thinking':False},'max_tokens':6000,'require_pass':True},'tts':{}})
cloud_tts=copy.deepcopy(settings['tts'])
local_speech_file=ROOT/'config.gpt-sovits.local.json'
local_speech=json.loads(local_speech_file.read_text('utf-8')).get('tts',{}) if local_speech_file.is_file() else {}
if local_speech:settings['tts']=copy.deepcopy(local_speech)
jobs={}
STYLE_IDS={'studio_noir','studio_editorial','studio_sketch'}
STUDIO_PROJECTS=ROOT/'video_projects'

@app.middleware('http')
async def local_origin(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:7860','http://localhost:7860','http://127.0.0.1:5173','http://localhost:5173'}:
            return JSONResponse({'detail':'请从本地工作台提交请求。'},status_code=403)
    return await call_next(request)

class Keys(BaseModel):
    text_key: str=Field(default='',max_length=512)
    vision_key: str=Field(default='',max_length=512)
    tts_provider: Literal['qwen_audio','gpt_sovits'] | None=None

@app.get('/api/config')
def config():
    return {'text_ready':bool(settings['text'].get('api_key')),'vision_ready':bool(settings['vision'].get('api_key')),
            'model':settings['text']['model'],'fallback_model':next(iter(settings['text'].get('fallback_models',[])),None),'fallback_models':settings['text'].get('fallback_models',[]),
            'vision_model':settings['vision'].get('model',''),'vision_fallback_models':settings['vision'].get('fallback_models',[]),'base_url':settings['text'].get('base_url',''),'tts_provider':settings['tts'].get('provider'),'local_tts_available':bool(local_speech),'speech_sample_available':(ROOT/'deliverables/speech/male_teacher_cpu.wav').is_file()}

@app.post('/api/config')
def save_config(keys:Keys):
    with lock:
        if keys.tts_provider=='gpt_sovits' and not local_speech:
            raise HTTPException(400,'请先安装本地语音并配置 config.gpt-sovits.local.json。')
        if keys.tts_provider=='qwen_audio' and cloud_tts.get('provider')!='qwen_audio':
            raise HTTPException(400,'请先在本机配置阿里云 TTS。')
        if keys.tts_provider:
            settings['tts']=copy.deepcopy(local_speech if keys.tts_provider=='gpt_sovits' else cloud_tts)
            if keys.tts_provider=='qwen_audio':settings['tts']['api_key']=settings['text'].get('api_key','')
        if keys.text_key.strip():
            settings['text']['api_key']=keys.text_key.strip()
            if settings['tts'].get('provider')=='qwen_audio':settings['tts']['api_key']=keys.text_key.strip()
        if keys.vision_key.strip():settings['vision']['api_key']=keys.vision_key.strip()
    return config()

@app.get('/api/speech/sample')
def speech_sample():
    file=ROOT/'deliverables/speech/male_teacher_cpu.wav'
    if not file.is_file():raise HTTPException(404,'配音试听尚未生成。')
    return FileResponse(file,media_type='audio/wav')

@app.get('/api/styles')
def styles():return [x for x in list_styles() if x['id'] in STYLE_IDS]

def update_job(identity,**values):
    with lock:
        jobs[identity].update(values)
        jobs[identity]['updated_at']=time.time()
        record=jobs[identity].copy()
    if record.get('project'):
        Path(record['project']).mkdir(parents=True,exist_ok=True)
        write_json(Path(record['project'])/'studio_job.json',{k:v for k,v in record.items() if k!='project'})

def work(identity,project,prompt,config,materials,resume=False):
    update_job(identity,status='running')
    try:
        def event(e):update_job(identity,stage=e['stage'],stage_status=e['status'],message=e['message'])
        gate=lambda stage,document:PlanningReview(project).checkpoint(stage,document)
        pipe=VideoPipeline(prompt,config,project/'output',project=project,materials=materials,on_event=event,resume=resume,planning_gate=gate)
        result=pipe.run()
        poster=project/'output/poster.jpg'
        try:
            run_command([ffmpeg_binary(),'-y','-ss',str(probe(result)['duration']*.55),'-i',str(result),'-frames:v','1','-vf','scale=960:-2',str(poster)])
        except Exception:
            pass
        update_job(identity,status='complete',video=f'/api/jobs/{identity}/video',poster=f'/api/jobs/{identity}/poster' if poster.is_file() else None,review=pipe.manifest.get('visual_review',{}),model=pipe.manifest.get('production_model'))
    except PlanningPending as pending:
        update_job(identity,status='awaiting_review',stage=pending.stage,message=str(pending))
    except Exception as e:
        update_job(identity,status='failed',message=sanitize_error(str(e),config)[:1500])
    finally:
        state={k:v for k,v in jobs[identity].items() if k!='project'}
        (project/'studio_job.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf8')

def discover():
    # Restartable library; only our studio job metadata is public.
    for project in STUDIO_PROJECTS.glob('*'):
        metadata=project/'studio_job.json'
        if metadata.is_file():
            try:
                record=json.loads(metadata.read_text(encoding='utf8'))
                if record.get('id') not in jobs or record.get('updated_at',0)>jobs[record['id']].get('updated_at',0):
                    if record.get('status') in ('running','queued','revising'):record.update(status='failed',message='服务已重启，请重新生成。')
                    jobs[record['id']]={**record,'project':str(project)}
            except (ValueError,KeyError):pass
    acceptance=ROOT/'deliverables'/'manifest.json'
    if acceptance.is_file():
        for item in json.loads(acceptance.read_text(encoding='utf8')).get('videos',[]):
            identity='baseline-'+item['style']
            existing=next((j for j in jobs.values() if j.get('project') and Path(j['project']).resolve()==(ROOT/item['project']).resolve()),None)
            if existing:
                existing.update(poster=f"/api/jobs/{existing['id']}/poster",poster_path=item['poster'])
                continue
            if identity not in jobs:jobs[identity]={'id':identity,'prompt':'六面体展开图：旋转移面找公共边','style':item['style'],'duration':item['duration'],'status':'complete','stage':'compose','message':'三种风格基准成片','video':f'/api/jobs/{identity}/video','path':item['file'],'poster':f'/api/jobs/{identity}/poster','poster_path':item['poster'],'review':{'passed':item.get('review_passed',False)}}

@app.get('/api/jobs')
def get_jobs():
    with lock:
        discover()
        return [{k:v for k,v in j.items() if k not in ('project','path','poster_path')} for j in reversed(list(jobs.values()))]

@app.post('/api/jobs',status_code=202)
async def create_job(prompt:Annotated[str,Form()],style:Annotated[str,Form()],duration:Annotated[int,Form()]=30,orientation:Annotated[str,Form()]='landscape',files:Annotated[list[UploadFile]|None,File()]=None,auto_approve:Annotated[bool,Form()]=False,reference_urls:Annotated[str,Form()]='',source_ids:Annotated[str,Form()]=''):
    if not 5<=len(prompt.strip())<=6000:raise HTTPException(400,'请填写5至6000字的视频需求。')
    if style not in STYLE_IDS:raise HTTPException(400,'请选择可用主题。')
    if not 15<=duration<=120 or orientation not in ('landscape','portrait'):raise HTTPException(400,'视频参数无效。')
    if not settings['text'].get('api_key') or not settings['vision'].get('api_key'):raise HTTPException(400,'请先配置生成与视觉审核 API Key。')
    if len(files or [])>10:raise HTTPException(400,'每次最多10份素材。')
    with lock:
        if any(j.get('status') in ('queued','running','revising') for j in jobs.values()):raise HTTPException(409,'已有视频正在生成，完成后即可开始下一个。')
    identity=uuid.uuid4().hex[:12];project=STUDIO_PROJECTS/f'studio-{identity}'
    upload_directory=project/'uploads';upload_directory.mkdir(parents=True)
    material=[]
    for index,upload in enumerate(files or []):
        name=f'{index:02d}-'+safe_name(upload.filename or 'material')
        target=upload_directory/name
        total=0
        with target.open('wb') as stream:
            while chunk:=await upload.read(1024*1024):
                total+=len(chunk)
                if total>50*1024*1024:
                    target.unlink(missing_ok=True)
                    raise HTTPException(413,'单份素材请控制在50 MB以内。')
                stream.write(chunk)
        material.append(target)
    urls=[u.strip() for u in reference_urls.splitlines() if u.strip()]
    if len(urls)>20:raise HTTPException(400,'每次最多20条参考链接。')
    from teaching_research import public_url
    try:
        for url in urls:public_url(url)
        chosen=json.loads(source_ids) if source_ids else []
        if not isinstance(chosen,list) or len(chosen)>20 or any(not isinstance(x,str) for x in chosen):raise ValueError('参考素材选择无效')
    except Exception:raise HTTPException(400,'请检查公开参考链接和素材选择。')
    c=copy.deepcopy(settings)
    c=merge(c,{'teaching_research':{'reference_urls':urls,'source_ids':chosen}})
    c=merge(c,{'style':style,'video':{'quality':'high','fps':30,'orientation':orientation,'target_duration':duration,'max_sections':1 if duration<=45 else 3,'max_beats':6,'render_timeout':900,'pause_seconds':.12},'assets':{'enabled':False}})
    c['video_overrides']={k:v for k,v in c['video'].items() if k in ('quality','fps','orientation','target_duration','max_sections','max_beats','render_timeout','pause_seconds')}
    with lock:jobs[identity]={'id':identity,'prompt':prompt.strip(),'style':style,'duration':duration,'status':'queued','stage':'outline','message':'已加入生成队列','project':str(project)}
    PlanningReview(project,auto_approve=auto_approve)
    update_job(identity,status='queued',auto_approve=auto_approve)
    executor.submit(work,identity,project,prompt.strip(),c,material)
    return {'id':identity}

@app.post('/api/jobs/{identity}/retry',status_code=202)
def retry(identity:str):
    record=jobs.get(identity)
    if not record or not record.get('project') or record.get('status')!='failed':raise HTTPException(400,'该任务无法重试。')
    if any(j.get('status') in ('queued','running','revising') for j in jobs.values()):raise HTTPException(409,'请等待当前任务完成。')
    project=Path(record['project'])
    manifest=json.loads((project/'output/manifest.json').read_text(encoding='utf8'))
    c=restore_credentials(manifest['config'],settings)
    c['vision']=merge(c['vision'],settings['vision'])
    if not (project/'planning_review.json').is_file():PlanningReview(project,auto_approve=True)
    runtime=project/'code/runtime'
    changed=any((runtime/name).is_file() and (runtime/name).read_bytes()!=(ROOT/'src'/name).read_bytes() for name in ('scene_runtime.py','series_style.py','handdrawn_runtime.py','handdrawn_bridge.cjs','studio_components.py','cube_geometry.py','rough_square.json'))
    if changed:
        # Archived runtimes are immutable. Upgrade by creating a new revision, not by editing old inputs.
        old=project
        requirements=old/'prompts/requirements.json'
        if requirements.is_file():
            previous_task=json.loads(requirements.read_text(encoding='utf8'))
            # Preserve explicitly authored baseline tasks during revision upgrades.
            if 'cube_lesson' in previous_task.get('prompts',{}).get('code',''):
                c['task']=merge(previous_task,{'component_profile':'cube_baseline'})
                c['video_overrides']=merge(c.get('video_overrides',{}),{'layout':'canvas','style_lock':False,'brand':'折解 / 空间推理'})
        project=STUDIO_PROJECTS/f'studio-{identity}-r{uuid.uuid4().hex[:4]}'
        materials=[f for f in (old/'input/materials').iterdir() if f.is_file() and f.name!='index.json']
        update_job(identity,status='queued',message='正在用更新后的主题重新生成',project=str(project),parent=old.name)
        executor.submit(work,identity,project,record['prompt'],c,materials,False)
    else:
        update_job(identity,status='queued',message='正在从已完成的步骤继续')
        executor.submit(work,identity,project,record['prompt'],c,[],True)
    return {'id':identity}

@app.get('/api/jobs/{identity}/video')
def video(identity:str):
    discover();record=jobs.get(identity)
    if not record or record.get('status')!='complete':raise HTTPException(404,'视频尚未就绪。')
    target=(ROOT/record['path']).resolve() if record.get('path') else Path(record['project'])/'output/final.mp4'
    if not target.is_relative_to(ROOT) or not target.is_file():raise HTTPException(404,'视频文件不存在。')
    return FileResponse(target,media_type='video/mp4',filename=f"{record['style']}-{identity}.mp4")

@app.get('/api/jobs/{identity}/poster')
def poster(identity:str):
    record=jobs.get(identity)
    if not record:raise HTTPException(404,'作品不存在。')
    target=(ROOT/record['poster_path']).resolve() if record.get('poster_path') else Path(record.get('project',''))/'output/poster.jpg'
    if not target.resolve().is_relative_to(ROOT) or not target.is_file():raise HTTPException(404,'预览尚未就绪。')
    return FileResponse(target,media_type='image/jpeg')

@app.get('/api/jobs/{identity}/report')
def report(identity:str):
    record=jobs.get(identity)
    if not record:raise HTTPException(404,'任务不存在。')
    if record.get('project'):
        p=Path(record['project'])/'output/manifest.json'
        if p.is_file():return json.loads(p.read_text(encoding='utf8'))
    return {'visual_review':record.get('review',{})}


class PlanningEdit(BaseModel):
    version: str=Field(min_length=64,max_length=64)
    document: dict

class PlanningRevision(PlanningEdit):
    feedback: str=Field(min_length=2,max_length=6000)

class PlanningApproval(BaseModel):
    version: str=Field(min_length=64,max_length=64)

class ReviewMode(BaseModel):
    auto_approve: bool

class SourceSearch(BaseModel):
    query: str=Field(min_length=2,max_length=200)
    platform: str='web'
    limit: int=Field(default=6,ge=1,le=12)

class SourceIngest(BaseModel):
    urls: list[str]=Field(min_length=1,max_length=20)


def reviewed_job(identity, editable=False):
    with lock:
        discover()
        record=jobs.get(identity)
        if not record or not record.get('project'):raise HTTPException(404,'任务不存在。')
        if editable and record.get('status')!='awaiting_review':raise HTTPException(409,'任务当前不处于等待确认状态。')
        return dict(record),Path(record['project'])


def planning_engine(record,project):
    # Editing validates against the frozen project without reinitializing its
    # manifest, credentials or generation state.
    from styles import StylePackage
    from video_project import read_templates
    manifest=json.loads((project/'output/manifest.json').read_text(encoding='utf8'))
    c=restore_credentials(manifest['config'],settings)
    snapshot=json.loads((project/'prompts/style.json').read_text(encoding='utf8'))
    pipe=VideoPipeline.__new__(VideoPipeline)
    pipe.config=c;pipe.topic=record['prompt'];pipe.project=project;pipe.output=project/'output'
    pipe.materials=json.loads((pipe.output/'materials.json').read_text(encoding='utf8'))
    pipe.templates=read_templates(project);pipe.style_snapshot=snapshot
    pipe.style=StylePackage(snapshot['id'],snapshot.get('title',''),snapshot.get('description',''),snapshot['video'],project/'prompts',snapshot['policy'],snapshot.get('version','1.0.0'),snapshot.get('technical',{}),snapshot.get('sources',[]))
    from project_extensions import read_extensions
    pipe.extensions=read_extensions(project/'code/runtime')
    pipe.teaching_research=None
    research=project/'output/teaching_research/research.json'
    if research.is_file():
        pipe.teaching_research=json.loads(research.read_text(encoding='utf8'))
        validate_plan(pipe.teaching_research['plan'],pipe.teaching_research['sources'])
    return pipe


def validate_document(pipe,stage,document):
    if stage=='outline':pipe.validate_outline(document)
    elif stage=='storyboard':pipe.validate_storyboard(document,json.loads((pipe.output/'outline.json').read_text(encoding='utf8')))
    else:raise ValueError('仅支持编辑大纲和分镜。')


def enqueue_resume(identity,project):
    record=jobs[identity]
    manifest=json.loads((project/'output/manifest.json').read_text(encoding='utf8'))
    c=restore_credentials(manifest['config'],settings)
    update_job(identity,status='queued',message='正在从已确认的内容继续生成')
    executor.submit(work,identity,project,record['prompt'],c,[],True)


@app.get('/api/jobs/{identity}/planning')
def get_planning(identity:str):
    record,project=reviewed_job(identity)
    snapshot=PlanningReview(project).snapshot()
    reference=project/'output/teaching_research/research.json'
    if reference.is_file():
        value=json.loads(reference.read_text(encoding='utf8'))
        snapshot['teaching_plan']=value['plan']
        snapshot['sources']=[{k:v for k,v in source.items() if k in ('id','title','url','sha256','kind','images')} for source in value['sources']]
    return {**snapshot,'status':record['status']}


@app.put('/api/jobs/{identity}/planning/{stage}')
def save_planning(identity:str,stage:str,edit:PlanningEdit):
    with lock:
        record,project=reviewed_job(identity,True)
        try:
            with project_lock(project):
                review=PlanningReview(project)
                pipe=planning_engine(record,project)
                validate_document(pipe,stage,edit.document)
                review.replace(stage,edit.document,edit.version)
                update_job(identity,status='awaiting_review',stage=stage,message='修改已保存，等待确认')
                return review.snapshot()
        except ReviewConflict as e:raise HTTPException(409,str(e))
        except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,sanitize_error(str(e),settings))


@app.post('/api/jobs/{identity}/planning/{stage}/revise',status_code=202)
def revise_planning(identity:str,stage:str,edit:PlanningRevision):
    with lock:
        record,project=reviewed_job(identity,True)
        if stage not in ('outline','storyboard'):raise HTTPException(400,'仅支持大纲和分镜。')
        try:
            review=PlanningReview(project)
            if stage not in review.snapshot()['documents']:raise ReviewConflict('该阶段尚未生成。')
            review.check_version(stage,edit.version)
        except ReviewConflict as e:raise HTTPException(409,str(e))
        update_job(identity,status='revising',stage=stage,message='AI 正在按意见修改，完成后仍需确认')
    executor.submit(revise_worker,identity,project,record,stage,edit)
    return {'id':identity,'status':'revising'}


def revise_worker(identity,project,record,stage,edit):
    try:
        with project_lock(project):
            pipe=planning_engine(record,project)
            validate_document(pipe,stage,edit.document)
            prompt=pipe.prompt(stage,'你是课程编辑。根据创作者修改意见修订当前'+('大纲' if stage=='outline' else '分镜')+'，保留全部字段、已核验事实、题目原文与选项、章节ID及来源证据。只返回完整JSON对象。\n当前文档：'+json.dumps(edit.document,ensure_ascii=False)+'\n修改意见（创作者要求）：'+edit.feedback)
            if stage=='storyboard':prompt+='\n已确认的大纲：'+json.dumps(PlanningReview(project).document('outline'),ensure_ascii=False)
            from pipeline import ModelGateway
            gateway=ModelGateway(pipe.config['text'])
            try:
                revised=gateway.json(prompt,lambda value:validate_document(pipe,stage,value))
            finally:
                if getattr(gateway,'client',None):gateway.client.close()
            PlanningReview(project).replace(stage,revised,edit.version,'ai',edit.feedback)
        update_job(identity,status='awaiting_review',stage=stage,message='AI 修改完成，请检查后确认')
    except Exception as error:
        update_job(identity,status='awaiting_review',stage=stage,message='AI 修改失败，已保留原稿：'+sanitize_error(str(error),settings)[:500])


@app.post('/api/jobs/{identity}/planning/{stage}/approve',status_code=202)
def approve_planning(identity:str,stage:str,approval:PlanningApproval):
    if stage not in ('outline','storyboard'):raise HTTPException(400,'仅支持大纲和分镜。')
    with lock:
        record,project=reviewed_job(identity,True)
        if any(j.get('status') in ('running','queued','revising') for j in jobs.values()):raise HTTPException(409,'请等待当前生成任务完成。')
        try:
            with project_lock(project):
                pipe=planning_engine(record,project)
                review=PlanningReview(project)
                validate_document(pipe,stage,review.document(stage))
                review.approve(stage,approval.version)
            enqueue_resume(identity,project)
        except ReviewConflict as e:raise HTTPException(409,str(e))
        except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,sanitize_error(str(e),settings))
    return {'id':identity}


@app.patch('/api/jobs/{identity}/planning-mode',status_code=202)
def set_planning_mode(identity:str,mode:ReviewMode):
    with lock:
        record,project=reviewed_job(identity,True)
        if any(j.get('status') in ('running','queued','revising') for j in jobs.values()):raise HTTPException(409,'请等待当前生成任务完成。')
        with project_lock(project):PlanningReview(project,auto_approve=mode.auto_approve)
        update_job(identity,auto_approve=mode.auto_approve)
        if mode.auto_approve:enqueue_resume(identity,project)
    return {'id':identity,'auto_approve':mode.auto_approve}


@app.post('/api/sources/search')
def search_sources(request:SourceSearch):
    try:
        service=TeachingSources(settings.get('teaching_research',{}))
        result=service.search(request.query,request.platform,request.limit)
        # Search summaries are candidates only. Reading/indexing is a separate operation.
        return result
    except Exception as e:raise HTTPException(502,sanitize_error(str(e),settings)[:900])


@app.post('/api/sources/ingest')
def ingest_sources(request:SourceIngest):
    service=TeachingSources(settings.get('teaching_research',{}));results=[]
    for url in request.urls:
        try:
            source=service.ingest(url)
            results.append({'status':'indexed',**{k:v for k,v in source.items() if k not in ('text','metadata')}})
        except Exception as e:results.append({'url':url,'status':'failed','error':sanitize_error(str(e),settings)[:700]})
    return {'results':results,**service.library.stats()}


@app.get('/api/sources/{identity}')
def get_source(identity:str):
    source=TeachingSources(settings.get('teaching_research',{})).library.get(identity)
    if not source:raise HTTPException(404,'素材不存在或尚未读取正文。')
    return source

if (ROOT/'web/dist').is_dir():app.mount('/',StaticFiles(directory=ROOT/'web/dist',html=True),name='web')

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=7860,log_level='info')
