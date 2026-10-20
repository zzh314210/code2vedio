"""Private editing jobs using the same signed worker identity and model channels."""
import copy,json,time,uuid,shutil
from pathlib import Path
from typing import Annotated,Literal
from fastapi import APIRouter,UploadFile,File,Form,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from configuration import sanitize_error
from video_project import write_json
from storage_lifecycle import user_directory,records as storage_records
from user_config import validate_public_endpoint
from editing import MODES,inspect_media,validate_clips,analyze,render,review_commerce,selected_subtitles
from model_gateway import ModelGateway

class EditPlan(BaseModel):
 version:int
 clips:list[dict]=Field(min_length=1,max_length=16)
 summary:str=Field(default='',max_length=600)
 subtitles:list[dict]|None=Field(default=None,max_length=300)

class EditingService:
 def __init__(self,root,user,config,executor,lock,video_busy,private,job_id):
  self.root=root;self.user=user;self.config=config;self.executor=executor;self.lock=lock;self.video_busy=video_busy;self.private=private;self.job_id=job_id;self.jobs={};self.router=APIRouter();self.queue=None;self.storage=None
  for path in storage_records(root,'editing_job.json'):
   try:
    job=json.loads(path.read_text());job['project']=str(path.parent)
    if job['status'] in ['uploading','analyzing','rendering']:
     job.update(status='failed',message='服务已重启，点击重试继续。');write_json(path,job)
    self.jobs[job['id']]=job
   except (ValueError,KeyError):pass
  self.routes()
 def busy(self):return any(j['status'] in ['uploading','analyzing','rendering'] for j in self.jobs.values())
 def directory(self,identity):return Path(self.jobs.get(identity,{}).get('project') or self.root/('edit-'+identity))
 def get(self,identity):
  job=self.jobs.get(identity)
  if not job or job['owner_id']!=self.user()['id']:raise HTTPException(404,'剪辑任务不存在。')
  return job
 def public(self,job):
  result={k:v for k,v in job.items() if k not in ('owner_id','project')}
  result['sources']=[{k:v for k,v in s.items() if k not in ['file','transcript','audio_peaks','scenes']} for s in result.get('sources',[])]
  if self.queue:
   state=self.queue.snapshot(job['id'])
   if state:result['queue']=state
  return copy.deepcopy(result)
 def update(self,identity,**values):
  with self.lock:
   job=self.jobs[identity];previous=job.get('status');job.update(values,updated_at=time.time())
   if self.storage:self.storage.stamp(job,previous)
   if self.queue:self.queue.progress(identity,job.get('stage','prepare'))
   write_json(self.directory(identity)/'editing_job.json',job)
 def schedule(self,identity,config,action):
  self.executor.submit(self.work,identity,copy.deepcopy(config),action)
 def work(self,identity,config,action):
  job=self.jobs[identity];directory=self.directory(identity)
  self.update(identity,status='analyzing' if action=='analyze' else 'rendering')
  def event(stage,message):self.update(identity,stage=stage,message=message)
  try:
   for role in ['text','vision']:
    validate_public_endpoint(config[role]['base_url'])
    config[role]['usage_file']=str(directory/'usage.jsonl')
    # Same metering; disabled automatic wallet charging remains unchanged.
    config[role]['billing_context']={'private':str(self.private),'user_id':job['owner_id'],'job_id':identity}
   if action=='analyze':
    sources,plan=analyze(directory,copy.deepcopy(job),config,event)
    self.update(identity,sources=sources,plan=plan,version=job.get('version',0)+1,status='awaiting_review',stage='review',message='方案已准备好，预览原片并确认选段后导出。')
   else:
    validate_clips(job['plan'],job['sources'],mode=job['mode'],speech_safe=job['mode']=='product')
    if job['mode']=='product':
     event('review','导出前复核商品、报价条件与语句完整性')
     review=review_commerce(directory,job['sources'],job['plan'],ModelGateway(config['text']))
     if not review['passed']:raise ValueError('当前选段未通过带货内容核对：'+'；'.join(review['issues'])[:240]+'。请调整方案后再导出。')
    actual=render(directory,copy.deepcopy(job),job['plan'],event)
    self.update(identity,status='complete',stage='complete',message='剪辑完成，可以预览和下载。',duration=actual['duration'],video=f'/api/edits/{identity}/video',poster=f'/api/edits/{identity}/poster')
  except Exception as error:
   detail=sanitize_error(str(error),config)
   write_json(directory/'error_details.json',{'type':type(error).__name__,'detail':detail[:6000]})
   safe=str(error) if isinstance(error,ValueError) and 'Traceback' not in str(error) and '/data/' not in str(error) and len(str(error))<400 else '本次素材处理未完成，请保留任务并重试；持续失败时请检查模型配置或换用标准 MP4 素材。'
   self.update(identity,status='failed',message=sanitize_error(safe,config),failed_action=action)
 def available(self):
  if self.queue:
   self.queue.ensure_capacity(self.user()['id']);return
  if self.video_busy() or self.busy():raise HTTPException(409,'当前已有任务在制作，完成后即可继续。')
 def ready(self):
  config=self.config()
  if any(not config[role].get(k) for role in ['text','vision'] for k in ['model','base_url','api_key']):raise HTTPException(400,'请先在模型配置页连接内容生成与视觉审核服务。')
  return config
 def routes(self):
  r=self.router
  @r.get('/api/edits')
  def listing():
   with self.lock:return [self.public(j) for j in sorted(self.jobs.values(),key=lambda j:j['created_at'],reverse=True) if j['owner_id']==self.user()['id']]
  @r.get('/api/edits/{identity}')
  def detail(identity:str):return self.public(self.get(identity))
  @r.post('/api/edits',status_code=202)
  async def create(prompt:Annotated[str,Form()],files:Annotated[list[UploadFile],File()],mode:Annotated[Literal['highlights','product','gaming','documentary'],Form()]='highlights',target_duration:Annotated[int,Form()]=30,orientation:Annotated[Literal['landscape','portrait'],Form()]='landscape',captions:Annotated[bool,Form()]=True):
   if not 5<=len(prompt.strip())<=3000:raise HTTPException(400,'请填写5至3000字的剪辑要求。')
   if not (30 if mode=='product' else 5)<=target_duration<=120:raise HTTPException(400,'普通剪辑目标为5至120秒；直播带货切片为30至120秒。')
   if not 1<=len(files)<=3:raise HTTPException(400,'每次可上传1至3个视频。')
   config=self.ready();identity=self.job_id() or uuid.uuid4().hex[:12];directory=user_directory(self.root,'edit',identity,self.user()['id'])
   with self.lock:
    self.available();directory.mkdir(parents=True)
    self.jobs[identity]={'id':identity,'owner_id':self.user()['id'],'project':str(directory),'prompt':prompt.strip(),'mode':mode,'target_duration':target_duration,'orientation':orientation,'captions':captions,'status':'uploading','stage':'upload','created_at':time.time(),'sources':[],'version':0}
   try:
    total=0;sources=[]
    for i,upload in enumerate(files):
     suffix=Path(upload.filename or '').suffix.lower()
     if suffix not in ['.mp4','.mov','.webm','.mkv']:raise HTTPException(400,'请上传 MP4、MOV、WebM 或 MKV 视频。')
     filename=f'source-{i}{suffix}';size=0
     with (directory/filename).open('wb') as stream:
      while chunk:=await upload.read(1024*1024):
       size+=len(chunk);total+=len(chunk)
       if size>150*1024*1024 or total>400*1024*1024:raise HTTPException(413,'每个视频最多150 MB，合计最多400 MB。')
       stream.write(chunk)
     import asyncio
     info=await asyncio.to_thread(inspect_media,directory/filename,900 if mode=='product' else 300)
     sources.append({'id':f's{i+1}','file':filename,'name':Path(upload.filename).name[:120],**info})
    if sum(x['duration'] for x in sources)>(1800 if mode=='product' else 600):raise HTTPException(400,'素材总时长超限：普通剪辑10分钟，直播带货切片30分钟。')
    if target_duration>sum(x['duration'] for x in sources)*1.4:raise HTTPException(400,'目标时长超过素材长度，请降低目标时长或补充素材。')
    self.update(identity,sources=sources,status='analyzing',stage='analyze',message='已收到视频，正在分析镜头与语音。')
    self.schedule(identity,config,'analyze');return {'id':identity}
   except BaseException as error:
    with self.lock:self.jobs.pop(identity,None)
    shutil.rmtree(directory,ignore_errors=True)
    if isinstance(error,ValueError):raise HTTPException(400,str(error))
    raise
  @r.put('/api/edits/{identity}/plan')
  def save(identity:str,value:EditPlan):
   with self.lock:
    job=self.get(identity)
    if job['status'] not in ['awaiting_review','complete','failed']:raise HTTPException(409,'分析或导出中，请稍后修改方案。')
    if value.version!=job['version']:raise HTTPException(409,'方案已更新，请刷新后重试。')
    try:plan=validate_clips(value.model_dump(),job['sources'],mode=job['mode'],speech_safe=job['mode']=='product')
    except ValueError as error:raise HTTPException(422,str(error))
    if value.subtitles is None:plan['subtitles']=selected_subtitles(plan,job['sources'])
    self.update(identity,plan=plan,version=job['version']+1,status='awaiting_review',stage='review',video=None,poster=None)
    return self.public(self.get(identity))
  @r.post('/api/edits/{identity}/render',status_code=202)
  def export(identity:str):
   with self.lock:
    job=self.get(identity)
    if job['status']!='awaiting_review':raise HTTPException(409,'请等待分析完成，确认剪辑方案后再导出。')
    self.available();config=self.ready()
    self.update(identity,status='rendering',stage='render',message='正在导出成片，可离开页面稍后回来。')
    self.schedule(identity,config,'render');return {'id':identity}
  @r.post('/api/edits/{identity}/retry',status_code=202)
  def retry(identity:str):
   with self.lock:
    job=self.get(identity)
    if job['status'] not in ('failed','cancelled'):raise HTTPException(409,'仅未完成的任务可以重试。')
    self.available();config=self.ready();action=job.get('failed_action','analyze')
    self.update(identity,status='analyzing' if action=='analyze' else 'rendering',stage=action,message='正在重试')
    self.schedule(identity,config,action);return {'id':identity}
  @r.get('/api/edits/{identity}/source/{source_id}')
  def original(identity:str,source_id:str):
   job=self.get(identity);source=next((s for s in job['sources'] if s['id']==source_id),None)
   if not source:raise HTTPException(404,'素材不存在。')
   return FileResponse(self.directory(identity)/source['file'])
  @r.get('/api/edits/{identity}/{kind}')
  def artifact(identity:str,kind:str):
   job=self.get(identity)
   names={'video':('final.mp4','video/mp4'),'poster':('poster.jpg','image/jpeg'),'subtitles':('subtitles.srt','text/plain'),'timeline':('timeline.json','application/json'),'project':('timeline.otio','application/json')}
   if kind not in names or job['status']!='complete':raise HTTPException(404,'成片尚未完成。')
   name,mime=names[kind];path=self.directory(identity)/name
   if not path.is_file():raise HTTPException(404,'文件不存在。')
   return FileResponse(path,media_type=mime,filename='Frame-'+identity+Path(name).suffix if kind in ['subtitles','timeline','project'] else None)
