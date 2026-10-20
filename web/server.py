"""Local FastAPI studio. Credentials remain in process memory, jobs use the existing pipeline."""
import copy
import mimetypes
import os
import json
import sys
import threading
import time
import uuid
import base64
import hashlib
import hmac
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'web'))
from configuration import load_config, merge, sanitize_error, public_config
from voices import voice_router
from user_config import visible_config, runtime_config, validate_public_endpoint
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
app.include_router(voice_router())
lock=threading.RLock()
executor=ThreadPoolExecutor(max_workers=1)
config_file=next((ROOT/name for name in ('config.qwen-tts.local.json','config.local.json','config.studio.example.json') if (ROOT/name).is_file()),None)
settings=load_config(config_file)
PRIVATE=Path(os.environ.get('C2V_ACCOUNT_DIR',ROOT/'private'))
current_user=ContextVar('studio_user',default=None)
current_config=ContextVar('studio_config',default=None)
current_job_id=ContextVar('job_id',default=None)
from background_music_api import BackgroundMusic
music_service=BackgroundMusic(ROOT,PRIVATE,lambda:current_user.get())
app.include_router(music_service.router)
config_cache={}
legacy_owner=None
production_queue=None
storage=None


def user_settings(owner_id=None):
    user=current_user.get()
    identity=owner_id or user['id']
    personal=current_config.get() if user and user['id']==identity else config_cache.get(identity)
    if personal is None:raise HTTPException(403,'请重新登录后重试。')
    return runtime_config(settings,personal,PRIVATE/'libraries'/identity/'sources.sqlite3')


def job_settings(record, frozen=None):
    current=user_settings(record['owner_id'])
    if not frozen:return current
    # Retain project layout but never reuse another user's credentials or library.
    result=restore_credentials(frozen,current)
    for role in ('text','vision','tts'):result[role]=copy.deepcopy(current[role])
    for resource in ('memory','cpus','pids_limit'):
        if resource in current.get('execution',{}):result.setdefault('execution',{})[resource]=current['execution'][resource]
    result.setdefault('teaching_research',{})['library']=current['teaching_research']['library']
    return result

jobs={}
STYLE_IDS={'studio_noir','studio_editorial','studio_sketch'}
STUDIO_PROJECTS=Path(os.environ.get('C2V_PROJECT_DIR',ROOT/'video_projects'))
from storage_lifecycle import UserStorage,user_directory,records as storage_records
storage=UserStorage(ROOT,STUDIO_PROJECTS,PRIVATE)
from editing_api import EditingService
editing_service=EditingService(STUDIO_PROJECTS,lambda:current_user.get(),user_settings,executor,lock,lambda:any(j.get('status') in ('queued','running','revising') for j in jobs.values()),PRIVATE,lambda:current_job_id.get())
app.include_router(editing_service.router)
from revision_api import RevisionAPI
revision_service=RevisionAPI(globals())
app.include_router(revision_service.router)

ALLOWED_ORIGINS={'http://127.0.0.1:7860','http://localhost:7860','http://127.0.0.1:5173','http://localhost:5173'}
ALLOWED_ORIGINS.update(origin.strip().rstrip('/') for origin in os.environ.get('C2V_ALLOWED_ORIGINS','').split(',') if origin.strip())

@app.middleware('http')
async def account_boundary(request,call_next):
    global legacy_owner
    encoded=request.headers.get('x-frame-context','')
    signature=request.headers.get('x-frame-signature','')
    try:
        key=(PRIVATE/'worker.key').read_bytes()
        target=request.url.path+('?' + request.url.query if request.url.query else '')
        expected=hmac.new(key,(request.method+'\n'+target+'\n'+encoded).encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):raise ValueError('signature')
        payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        if abs(time.time()-payload['time'])>90:raise ValueError('expired')
        user=payload['user']
        if not __import__('re').fullmatch('[a-f0-9]{32}',user['id']):raise ValueError('identity')
    except Exception:
        return JSONResponse({'detail':'仅允许网站后端调用。'},status_code=403)
    legacy_owner=payload['admin_id']
    token=current_user.set(user)
    config_token=current_config.set(payload['config'])
    job_token=current_job_id.set(payload.get('job_id'))
    with lock:config_cache[user['id']]=payload['config']
    try:
        if request.url.path.startswith('/api/jobs/'):
            identity=request.url.path.split('/')[3]
            with lock:
                discover()
                record=jobs.get(identity)
            if not record or record.get('owner_id')!=user['id']:
                return JSONResponse({'detail':'作品不存在。'},status_code=404)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        return response
    finally:
        current_user.reset(token)
        current_config.reset(config_token)
        current_job_id.reset(job_token)


@app.get('/api/styles')
def styles():return [x for x in list_styles() if x['id'] in STYLE_IDS]

def update_job(identity,**values):
    with lock:
        if values.get('stage',jobs[identity].get('stage'))!=jobs[identity].get('stage') or (values.get('status')=='running' and jobs[identity].get('status')!='running'):
            values['stage_started_at']=time.time()
        previous=jobs[identity].get('status')
        jobs[identity].update(values)
        storage.stamp(jobs[identity],previous)
        if production_queue:production_queue.progress(identity,jobs[identity].get('stage','prepare'))
        jobs[identity]['updated_at']=time.time()
        record=jobs[identity].copy()
    if record.get('project'):
        Path(record['project']).mkdir(parents=True,exist_ok=True)
        write_json(Path(record['project'])/'studio_job.json',{k:v for k,v in record.items() if k!='project'})

def work(identity,project,prompt,config,materials,resume=False):
    update_job(identity,status='running')
    try:
        for role in ('text','vision'):
            validate_public_endpoint(config[role]['base_url'])
        if config['tts'].get('provider')=='openai':validate_public_endpoint(config['tts']['base_url'])
        def event(e):update_job(identity,stage=e['stage'],stage_status=e['status'],message=e['message'])
        gate=lambda stage,document:PlanningReview(project).checkpoint(stage,document)
        for role in ('text','vision','tts'):
            config[role]['usage_file']=str(project/'usage.jsonl')
            config[role]['billing_context']={'private':str(PRIVATE),'user_id':jobs[identity]['owner_id'],'job_id':identity}
        pipe=VideoPipeline(prompt,config,project/'output',project=project,materials=materials,on_event=event,resume=resume,planning_gate=gate)
        result=pipe.run()
        poster=project/'output/poster.jpg'
        try:
            run_command([ffmpeg_binary(),'-y','-ss',str(probe(result)['duration']*.55),'-i',str(result),'-frames:v','1','-vf','scale=960:-2',str(poster)])
        except Exception:
            pass
        update_job(identity,status='complete',video=f'/api/jobs/{identity}/video',subtitles=f'/api/jobs/{identity}/subtitles',poster=f'/api/jobs/{identity}/poster' if poster.is_file() else None,review=pipe.manifest.get('visual_review',{}),model=pipe.manifest.get('production_model'))
    except PlanningPending as pending:
        update_job(identity,status='awaiting_review',stage=pending.stage,message=str(pending))
    except Exception as e:
        update_job(identity,status='failed',message=sanitize_error(str(e),config)[:1500])
    finally:
        state={k:v for k,v in jobs[identity].items() if k!='project'}
        (project/'studio_job.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf8')

def discover():
    # Restartable library; only our studio job metadata is public.
    for metadata in storage_records(STUDIO_PROJECTS,'studio_job.json'):
        project=metadata.parent
        if metadata.is_file():
            try:
                record=json.loads(metadata.read_text(encoding='utf8'))
                if record.get('id') not in jobs or record.get('updated_at',0)>jobs[record['id']].get('updated_at',0):
                    if record.get('status') in ('running','queued','revising') and not (production_queue and production_queue.has_pending(record['id'])):record.update(status='failed',message='服务已重启，请重新生成。')
                    jobs[record['id']]={**record,'owner_id':record.get('owner_id') or legacy_owner,'project':str(project)}
            except (ValueError,KeyError):pass
    for expired in storage.expired_records('video'):
        jobs[expired['id']]=expired
    acceptance=ROOT/'deliverables'/'manifest.json'
    if acceptance.is_file():
        for item in json.loads(acceptance.read_text(encoding='utf8')).get('videos',[]):
            identity='baseline-'+item['style']
            if identity in jobs and not jobs[identity].get('owner_id'):jobs[identity]['owner_id']=legacy_owner
            existing=next((j for j in jobs.values() if j.get('project') and Path(j['project']).resolve()==(ROOT/item['project']).resolve()),None)
            if existing:
                existing.update(poster=f"/api/jobs/{existing['id']}/poster",poster_path=item['poster'])
                continue
            if identity not in jobs:jobs[identity]={'id':identity,'owner_id':legacy_owner,'prompt':'六面体展开图：旋转移面找公共边','style':item['style'],'duration':item['duration'],'status':'complete','stage':'compose','message':'三种风格基准成片','video':f'/api/jobs/{identity}/video','path':item['file'],'poster':f'/api/jobs/{identity}/poster','poster_path':item['poster'],'review':{'passed':item.get('review_passed',False)}}

@app.get('/api/jobs')
def get_jobs():
    with lock:
        discover()
        return [public_job(j) for j in reversed(list(jobs.values())) if j.get('owner_id')==current_user.get()['id']]

def public_job(record):
    result={k:v for k,v in record.items() if k not in ('project','path','poster_path','owner_id','revision_request_id')}
    if production_queue:
        queue_state=production_queue.snapshot(record['id'])
        if queue_state:result['queue']=queue_state
    result['can_revise']=bool(record.get('status')=='complete' and record.get('project') and all((Path(record['project'])/'output'/name).is_file() for name in ('final.mp4','manifest.json','outline.json','storyboard.json')))
    selection=Path(record['project'])/'input/background_music/selection.json' if record.get('project') else None
    if selection and selection.is_file():
        result['background_music']=json.loads(selection.read_text(encoding='utf8'))
        if result.get('status')=='complete' and result['background_music'].get('credit'):
            result['music_credit']=f"/api/jobs/{record['id']}/music-credit"
    return result

@app.get('/api/jobs/{identity}')
def get_job(identity:str):
    with lock:
        discover()
        record=jobs.get(identity)
        if not record:raise HTTPException(404,'作品不存在。')
        return public_job(record)


@app.post('/api/jobs',status_code=202)
async def create_job(prompt:Annotated[str,Form()],style:Annotated[str,Form()],duration:Annotated[int,Form()]=30,orientation:Annotated[str,Form()]='landscape',files:Annotated[list[UploadFile]|None,File()]=None,auto_approve:Annotated[bool,Form()]=False,reference_urls:Annotated[str,Form()]='',source_ids:Annotated[str,Form()]='',template_id:Annotated[str,Form()]='',bgm_enabled:Annotated[bool,Form()]=False,bgm_track_id:Annotated[str,Form()]='',bgm_upload_id:Annotated[str,Form()]='',bgm_volume:Annotated[float,Form()]=.16):
    if not 5<=len(prompt.strip())<=6000:raise HTTPException(400,'请填写5至6000字的视频需求。')
    if style not in STYLE_IDS:raise HTTPException(400,'请选择可用主题。')
    if not 15<=duration<=(300 if template_id=='notes' else 120) or orientation not in ('landscape','portrait'):raise HTTPException(400,'视频参数无效。')
    if production_queue:production_queue.ensure_capacity(current_user.get()['id'])
    personal=user_settings()
    if not visible_config(current_config.get())['speech_ready']:raise HTTPException(400,'请完善配音服务配置。')
    if not all(personal[role].get(key) for role in ('text','vision') for key in ('api_key','model','base_url')):raise HTTPException(400,'请先配置生成与视觉审核 API Key。')
    if len(files or [])>10:raise HTTPException(400,'每次最多10份素材。')
    music,music_source=music_service.select(bgm_enabled,bgm_track_id,bgm_upload_id,bgm_volume)
    with lock:
        if not production_queue and (editing_service.busy() or any(j.get('status') in ('queued','running','revising') for j in jobs.values())):raise HTTPException(409,'已有视频正在生成，完成后即可开始下一个。')
    identity=current_job_id.get() or uuid.uuid4().hex[:12];project=user_directory(STUDIO_PROJECTS,'studio',identity,current_user.get()['id'])
    try:
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
        from video_templates import apply_template
        try:c=apply_template(personal,template_id)
        except ValueError as error:raise HTTPException(400,str(error))
        library=TeachingSources(personal['teaching_research']).library
        if any(not library.get(source_id) for source_id in chosen):raise HTTPException(400,'所选素材不在你的素材库中，请重新选择。')
        if template_id=='notes':
            from materials import load_materials
            try:
                if any(path.suffix.lower() not in {'.txt','.md','.markdown','.pdf'} for path in material):raise ValueError('笔记请使用 TXT、Markdown 或可复制文字的 PDF。')
                note_data=load_materials(material,prompt,c['materials'])
                if sum(len(x['text']) for x in note_data['selected_chunks'])<40:raise ValueError('请上传至少40字的笔记：支持 TXT、Markdown 和可复制文字的 PDF；扫描件请先转成文字。')
                if note_data['omitted_chunks']:raise ValueError('笔记超过本课容量，请按章节拆分上传，避免复盘遗漏。')
            except Exception as error:
                import shutil
                shutil.rmtree(project,ignore_errors=True)
                message=str(error) if isinstance(error,ValueError) and not isinstance(error,UnicodeError) else '无法读取这份笔记，请使用 UTF-8 文本或可复制文字的 PDF。'
                raise HTTPException(400,message)
        c=merge(c,{'teaching_research':{'reference_urls':urls,'source_ids':chosen,'enabled':'auto' if urls or chosen else False}})
        c=merge(c,{'style':style,'video':{'quality':'high','fps':30,'orientation':orientation,'target_duration':duration,'max_sections':min(6,max(1,__import__('math').ceil(duration/60))),'max_beats':6,'render_timeout':900,'pause_seconds':.12},'assets':{'enabled':False}})
        c['video_overrides']={k:v for k,v in c['video'].items() if k in ('quality','fps','orientation','target_duration','max_sections','max_beats','render_timeout','pause_seconds')}
        c['background_music']=music_service.freeze(music,music_source,project)
        with lock:
            if not production_queue and (editing_service.busy() or any(j.get('status') in ('queued','running','revising') for j in jobs.values())):
                import shutil
                shutil.rmtree(project,ignore_errors=True)
                raise HTTPException(409,'已有视频正在生成，请稍后重试。')
            jobs[identity]={'id':identity,'owner_id':current_user.get()['id'],'prompt':prompt.strip(),'style':style,'duration':duration,'template_id':template_id,'status':'queued','stage':'outline','message':'已加入生成队列','created_at':time.time(),'stage_started_at':time.time(),'project':str(project)}
        PlanningReview(project,auto_approve=auto_approve)
        update_job(identity,status='queued',auto_approve=auto_approve)
        executor.submit(work,identity,project,prompt.strip(),c,material)
        return {'id':identity}
    except Exception:
        if identity not in jobs:
            import shutil
            shutil.rmtree(project,ignore_errors=True)
        elif production_queue and not production_queue.has_pending(identity):
            update_job(identity,status='failed',message='任务未能加入队列，请稍后重试。')
        raise


@app.post('/api/jobs/{identity}/retry',status_code=202)
def retry(identity:str):
    with lock:
        record=jobs.get(identity)
        if not record or not record.get('project') or record.get('status') not in ('failed','cancelled'):raise HTTPException(400,'该任务无法重试。')
        if production_queue:production_queue.ensure_capacity(record['owner_id'])
        if not production_queue and (editing_service.busy() or any(j.get('status') in ('queued','running','revising') for j in jobs.values())):raise HTTPException(409,'请等待当前任务完成。')
        if record.get('revision_parent') and not record.get('revision_prepared'):
            return revision_service.retry(identity,record)
        project=Path(record['project'])
        if not (project/'output/manifest.json').is_file():
            c=job_settings(record)
            c=merge(c,{'style':record['style'],'video':{'target_duration':record['duration']}})
            music_selection=project/'input/background_music/selection.json'
            if music_selection.is_file():c['background_music']=json.loads(music_selection.read_text())
            materials=list((project/'uploads').glob('*'))
            update_job(identity,status='queued',message='正在重新启动未完成的生成步骤')
            executor.submit(work,identity,project,record['prompt'],c,materials,False)
            return {'id':identity}
        manifest=json.loads((project/'output/manifest.json').read_text(encoding='utf8'))
        c=job_settings(record,manifest['config'])
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
            project=user_directory(STUDIO_PROJECTS,'studio',identity+'-r'+uuid.uuid4().hex[:4],record['owner_id'])
            music_directory=old/'input/background_music'
            if music_directory.is_dir():
                import shutil
                shutil.copytree(music_directory,project/'input/background_music')
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

@app.get('/api/jobs/{identity}/subtitles')
def subtitles(identity:str):
    record=jobs.get(identity)
    if not record or not record.get('project'):raise HTTPException(404,'字幕尚未就绪。')
    target=Path(record['project'])/'output/subtitles.srt'
    if not target.is_file():raise HTTPException(404,'字幕尚未就绪。')
    import re
    content=re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})',r'\1.\2',target.read_text(encoding='utf8'))
    return Response('WEBVTT\n\n'+content,media_type='text/vtt')


@app.get('/api/jobs/{identity}/music-credit')
def music_credit(identity:str):
    record=jobs.get(identity)
    if not record or record.get('status')!='complete' or not record.get('project'):
        raise HTTPException(404,'音乐署名尚未就绪。')
    target=Path(record['project'])/'output/music-credit.txt'
    if not target.is_file():raise HTTPException(404,'此作品无需附加音乐署名。')
    return FileResponse(target,media_type='text/plain; charset=utf-8',filename='music-credit.txt')


@app.get('/api/jobs/{identity}/poster')
def poster(identity:str):
    record=jobs.get(identity)
    if not record:raise HTTPException(404,'作品不存在。')
    target=(ROOT/record['poster_path']).resolve() if record.get('poster_path') else Path(record.get('project',''))/'output/poster.jpg'
    if not target.resolve().is_relative_to(ROOT) or not target.is_file():raise HTTPException(404,'预览尚未就绪。')
    return FileResponse(target,media_type='image/jpeg')

@app.get('/api/jobs/{identity}/usage')
def job_usage(identity:str):
    record=jobs[identity]
    if not (current_config.get() or {}).get('use_platform'):
        return {'events':[],'unmetered_calls':0}
    path=Path(record.get('project',''))/'usage.jsonl'
    events=[]
    if path.is_file():
        for line in path.read_text().splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
    return {'events':events,'unmetered_calls':sum(not event.get('metered') for event in events)}


@app.get('/api/jobs/{identity}/report')
def report(identity:str):
    record=jobs.get(identity)
    if not record:raise HTTPException(404,'任务不存在。')
    if record.get('project'):
        p=Path(record['project'])/'output/manifest.json'
        if p.is_file():
            manifest=json.loads(p.read_text(encoding='utf8'))
            return {key:public_config(manifest[key]) for key in ('visual_review','production_model','status','stages') if key in manifest}
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
    platform: Literal['web','wikipedia','library']='wikipedia'
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


def planning_engine(record,project,runtime=None):
    # Editing validates against the frozen project without reinitializing its
    # manifest, credentials or generation state.
    from styles import StylePackage
    from video_project import read_templates
    manifest=json.loads((project/'output/manifest.json').read_text(encoding='utf8'))
    c=runtime or job_settings(record,manifest['config'])
    snapshot=json.loads((project/'prompts/style.json').read_text(encoding='utf8'))
    pipe=VideoPipeline.__new__(VideoPipeline)
    for role in ('text','vision','tts'):
        c[role]['usage_file']=str(project/'usage.jsonl')
        c[role]['billing_context']={'private':str(PRIVATE),'user_id':record['owner_id'],'job_id':record['id']}
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
    if production_queue:production_queue.ensure_capacity(record['owner_id'])
    manifest=json.loads((project/'output/manifest.json').read_text(encoding='utf8'))
    c=job_settings(record,manifest['config'])
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
        except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,sanitize_error(str(e),user_settings()))


@app.post('/api/jobs/{identity}/planning/{stage}/revise',status_code=202)
def revise_planning(identity:str,stage:str,edit:PlanningRevision):
    with lock:
        record,project=reviewed_job(identity,True)
        if production_queue:production_queue.ensure_capacity(record['owner_id'])
        if not production_queue and (editing_service.busy() or any(j.get('status') in ('queued','running','revising') for j in jobs.values())):raise HTTPException(409,'请等待当前任务完成。')
        if stage not in ('outline','storyboard'):raise HTTPException(400,'仅支持大纲和分镜。')
        try:
            review=PlanningReview(project)
            if stage not in review.snapshot()['documents']:raise ReviewConflict('该阶段尚未生成。')
            review.check_version(stage,edit.version)
        except ReviewConflict as e:raise HTTPException(409,str(e))
        runtime=job_settings(record)
        update_job(identity,status='revising',stage=stage,message='AI 正在按意见修改，完成后仍需确认')
        executor.submit(revise_worker,identity,project,record,stage,edit,runtime)
    return {'id':identity,'status':jobs[identity]['status']}


def revise_worker(identity,project,record,stage,edit,runtime):
    update_job(identity,status='revising',message='AI 正在按意见修改，完成后仍需确认')
    try:
        with project_lock(project):
            pipe=planning_engine(record,project,runtime)
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
        update_job(identity,status='awaiting_review',stage=stage,message='AI 修改失败，已保留原稿：'+sanitize_error(str(error),runtime)[:500])


@app.post('/api/jobs/{identity}/planning/{stage}/approve',status_code=202)
def approve_planning(identity:str,stage:str,approval:PlanningApproval):
    if stage not in ('outline','storyboard'):raise HTTPException(400,'仅支持大纲和分镜。')
    with lock:
        record,project=reviewed_job(identity,True)
        if production_queue:production_queue.ensure_capacity(record['owner_id'])
        if not production_queue and (editing_service.busy() or any(j.get('status') in ('running','queued','revising') for j in jobs.values())):raise HTTPException(409,'请等待当前生成任务完成。')
        try:
            with project_lock(project):
                pipe=planning_engine(record,project)
                review=PlanningReview(project)
                validate_document(pipe,stage,review.document(stage))
                review.approve(stage,approval.version)
            enqueue_resume(identity,project)
        except ReviewConflict as e:raise HTTPException(409,str(e))
        except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,sanitize_error(str(e),user_settings()))
    return {'id':identity}


@app.patch('/api/jobs/{identity}/planning-mode',status_code=202)
def set_planning_mode(identity:str,mode:ReviewMode):
    with lock:
        record,project=reviewed_job(identity,True)
        if mode.auto_approve and production_queue:production_queue.ensure_capacity(record['owner_id'])
        if not production_queue and (editing_service.busy() or any(j.get('status') in ('running','queued','revising') for j in jobs.values())):raise HTTPException(409,'请等待当前生成任务完成。')
        with project_lock(project):PlanningReview(project,auto_approve=mode.auto_approve)
        update_job(identity,auto_approve=mode.auto_approve)
        if mode.auto_approve:enqueue_resume(identity,project)
    return {'id':identity,'auto_approve':mode.auto_approve}


@app.post('/api/sources/search')
def search_sources(request:SourceSearch):
    try:
        service=TeachingSources({**user_settings().get('teaching_research',{}),'timeout':10})
        result=service.search_readable(request.query,request.platform,request.limit)
        return {'results':[{k:v for k,v in item.items() if k in ('id','url','title','kind','text')} for item in result['results']], 'unreadable_count':result.get('unreadable_count',0)}
    except Exception as e:raise HTTPException(502,'百科服务暂时无法连接，请稍后再试；也可使用我的素材库或上传文稿。')


@app.post('/api/sources/ingest')
def ingest_sources(request:SourceIngest):
    service=TeachingSources(user_settings().get('teaching_research',{}));results=[]
    for url in request.urls:
        try:
            source=service.ingest(url)
            results.append({'status':'indexed',**{k:v for k,v in source.items() if k not in ('text','metadata')}})
        except Exception as e:
            import requests
            from urllib.parse import urlsplit
            host=urlsplit(url).hostname or ''
            if host=='bilibili.com' or host.endswith('.bilibili.com'):
                message='此视频未提供可读取的公开字幕，请上传字幕或文稿。'
            elif isinstance(e,requests.exceptions.Timeout):message='原网站响应超时，请稍后重试或上传文稿。'
            elif isinstance(e,requests.exceptions.HTTPError) and e.response is not None and e.response.status_code in (401,403,429):message='原网站限制自动读取或要求登录，请上传你有权使用的文稿。'
            else:message='此链接没有可读取的完整正文，请换用公开文章或上传文稿。'
            results.append({'url':url,'status':'failed','error':message})
    return {'results':results,**service.library.stats()}


@app.get('/api/sources/{identity}')
def get_source(identity:str):
    source=TeachingSources(user_settings().get('teaching_research',{})).library.get(identity)
    if not source:raise HTTPException(404,'素材不存在或尚未读取正文。')
    return source

@app.get('/api/sources')
def list_sources():
    service=TeachingSources(user_settings()['teaching_research'])
    return {'results':service.library.search('',50)}



from queue_api import register_queue
register_queue(globals())

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,uds=str(PRIVATE/'worker.sock'),log_level='info')
