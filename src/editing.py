"""Evidence-led editing: local analysis, configured APIs, validated cuts, FFmpeg export.

Workflow research and provenance: deploy/EDITING_RESEARCH.md.
The model produces data only, never executable FFmpeg arguments or Python code.
"""
import copy,hashlib,json,math,os,re,subprocess,sys,wave
from pathlib import Path
from media import ffmpeg_binary,run_command,write_subtitles
from model_gateway import ModelGateway
from video_project import write_json
ROOT=Path(__file__).resolve().parents[1]
from editing_prompts import TEMPLATES, VERSION as EDITING_VERSION, observation_prompt, planning_prompt, review_prompt
MODES={key:{'title':value['title'],'direction':value['select']} for key,value in TEMPLATES.items()}

def execute(args,timeout=180):
 return run_command(args,timeout=timeout,env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'})

def inspect_media(path,max_seconds=300):
 raw=execute(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(path)],30)
 data=json.loads(raw);videos=[s for s in data['streams'] if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')]
 if not videos:raise ValueError('文件没有可读取的视频画面，请上传 MP4、MOV 或 WebM。')
 v=videos[0];duration=float(data.get('format',{}).get('duration',0));w,h=int(v['width']),int(v['height'])
 if not math.isfinite(duration) or not 1<=duration<=max_seconds:raise ValueError(f'单个视频时长需为1秒至{int(max_seconds/60)}分钟。')
 if w*h>3840*2160 or min(w,h)<32:raise ValueError('请上传分辨率不超过4K的视频。')
 if not any(f in data['format'].get('format_name','').split(',') for f in ['mov','mp4','matroska','webm']):raise ValueError('目前支持 MP4、MOV、WebM 视频容器。')
 return {'duration':round(duration,3),'width':w,'height':h,'has_audio':any(s.get('codec_type')=='audio' for s in data['streams'])}

def frame(source,path,at):
 execute([ffmpeg_binary(),'-v','error','-nostdin','-y','-threads','2','-ss',str(at),'-protocol_whitelist','file,pipe','-i',str(source),'-frames:v','1','-vf','scale=640:-2','-threads','2',str(path)],45)

def validate_clips(value,sources,target=None,mode=None,speech_safe=False):
 if not isinstance(value,dict) or not isinstance(value.get('clips'),list) or not 1<=len(value['clips'])<=16:raise ValueError('剪辑方案需包含1至16个片段。')
 known={s['id']:s for s in sources};normalized=[];used={};elapsed=0
 for item in value['clips']:
  if not isinstance(item,dict) or item.get('source_id') not in known:raise ValueError('剪辑片段引用了不存在的素材。')
  if isinstance(item.get('start'),bool) or isinstance(item.get('end'),bool):raise ValueError('片段时间无效。')
  try:start,end=float(item['start']),float(item['end'])
  except (TypeError,ValueError,KeyError):raise ValueError('片段起止时间必须为秒数。')
  if not all(math.isfinite(n) for n in [start,end]) or start<0 or end>known[item['source_id']]['duration']+.04 or end-start<.5:raise ValueError('片段需至少0.5秒，且不能超出原片范围。')
  if speech_safe:
   for cue in known[item['source_id']].get('transcript',[]):
    for edge in [start,end]:
     if cue['start']+.35<edge<cue['end']-.35:
      raise ValueError(f"剪点{edge:.2f}秒截断原句，请使用{cue['start']:.2f}至{cue['end']:.2f}秒的完整语句边界。")
  start=round(start*30)/30;end=min(round(end*30)/30,known[item['source_id']]['duration'])
  if any(start<b-.02 and end>a+.02 for a,b in used.get(item['source_id'],[])):raise ValueError('片段存在重复区间，请调整时间，避免重复播放。')
  if mode=='gaming' and used.get(item['source_id']) and start<used[item['source_id']][-1][0]:raise ValueError('游戏片段须按原片事件顺序排列，不能先播放结果再跳回铺垫。')
  used.setdefault(item['source_id'],[]).append((start,end))
  effect=item.get('effect','none')
  if effect not in ['none','focus']:raise ValueError('不支持此动效。')
  normalized.append({'source_id':item['source_id'],'start':round(start,3),'end':round(end,3),'reason':str(item.get('reason',''))[:300],'effect':effect,'output_start':round(elapsed,3)})
  elapsed+=end-start
 if mode=='product' and not 30<=round(elapsed,2)<=120:raise ValueError('直播带货成片需为30至120秒，请保留完整销售内容并调整选段。')
 if elapsed>180:raise ValueError('当前精剪成片最长3分钟。')
 if target and not max(3,target*.6)<=elapsed<=target*1.4:raise ValueError(f'剪辑时长{elapsed:.1f}秒偏离目标{target}秒，请精简或补充完整片段。')
 if sum(x['effect']=='focus' for x in normalized)>TEMPLATES.get(mode,{}).get('max_focus',3):raise ValueError(f"当前模板最多使用{TEMPLATES.get(mode,{}).get('max_focus',3)}处轻聚焦动效。")
 result={'clips':normalized,'duration':round(elapsed,3),'summary':str(value.get('summary',''))[:600]}
 captions=value.get('subtitles')
 if captions is not None:
  if not isinstance(captions,list) or len(captions)>300:raise ValueError('字幕数量超限。')
  valid=[];last_end=0
  for cue in captions:
   try:start,end=float(cue['start']),float(cue['end']);text=cue['text']
   except (KeyError,TypeError,ValueError):raise ValueError('字幕格式无效。')
   if not all(math.isfinite(t) for t in [start,end]) or start<last_end-.03 or end<=start or end>elapsed+.05 or not isinstance(text,str) or not 1<=len(text.strip())<=160:raise ValueError('字幕需按时间排列、不重叠，且不超过成片范围，每条1至160字。')
   valid.append({'start':round(start,3),'end':round(end,3),'text':text.strip().replace('\n',' ')})
   last_end=end
  result['subtitles']=valid
 return result

def budget_plan(value,sources,target,mode):
 """Fit whole, complete speech clips to the target; never trim a sentence to fit.

 The model chooses semantic ranges. A small frame-budget dynamic program handles
 arithmetic, preserving their order and explicit must-keep clips.
 """
 plan=validate_clips(value,sources,mode=None,speech_safe=True)
 lower=max(30 if mode=='product' else 3,target*.85)
 upper=min(120 if mode=='product' else 180,target*1.15)
 if lower<=plan['duration']<=upper:return validate_clips(value,sources,target,mode,True)
 # A highlight is allowed to be shorter when the model gives evidence-specific
 # reasons. Show the actual shortfall before confirmation; never pad with filler.
 shorter=value.get('shorter_reason')
 if mode!='product' and 5<=plan['duration']<lower and isinstance(shorter,str) and 10<=len(shorter.strip())<=400:
  result=validate_clips(value,sources,mode=mode,speech_safe=True)
  result['summary']=f'可用重点约{round(plan["duration"])}秒（目标{target}秒）。'+shorter.strip()+' '+result['summary']
  result['summary']=result['summary'][:600]
  return result
 limit=round(upper*30);states={0:(0,[])}
 for i,clip in enumerate(plan['clips']):
  frames=round((clip['end']-clip['start'])*30)
  raw=value['clips'][i];priority=raw.get('priority',3)
  if isinstance(priority,bool) or not isinstance(priority,(int,float)) or not math.isfinite(priority):priority=3
  priority=max(1,min(5,priority));required=raw.get('required') is True
  next_states={} if required else dict(states)
  for duration,(score,indices) in states.items():
   new=duration+frames
   if new<=limit:
    candidate=(score+priority*frames,indices+[i])
    if new not in next_states or candidate[0]>next_states[new][0]:next_states[new]=candidate
  states=next_states
 candidates=[(duration,value) for duration,value in states.items() if duration>=round(lower*30)]
 if not candidates:
  lengths=[round(c['end']-c['start'],2) for c in plan['clips']]
  required=sum(n for n,c in zip(lengths,value['clips']) if c.get('required') is True)
  raise ValueError(f'目标范围{lower:.1f}至{upper:.1f}秒，但各段长度{lengths}，合计{sum(lengths):.1f}秒，required合计{required:.1f}秒，无法组合。请重新选择完整句的时间范围：不足时补充相关原话，超时则删除次要内容；仅商品身份、报价限制、不可缺少的结论标required，不要把全部卖点都标为必选。')
 duration,(_,indices)=max(candidates,key=lambda x:x[1][0]-abs(x[0]-target*30)*3)
 result={**value,'clips':[value['clips'][i] for i in indices],'summary':'优先保留高价值的完整语句与画面，按目标时长组合选段；请逐段预览确认叙事连贯。'}
 return validate_clips(result,sources,target,mode,True)

def analyze(directory,record,config,event):
 directory=Path(directory);sources=record['sources'];observations=[]
 python=ROOT/'.venv-editing/bin/python';model=ROOT/'private/models/whisper-small'
 if not (model/'model.bin').is_file():model=ROOT/'private/models/whisper-base'
 if not python.is_file() or not (model/'model.bin').is_file():raise ValueError('本地视频分析组件尚未就绪，请稍后重试。')
 vision=ModelGateway(config['vision'],'vision');text=ModelGateway(config['text'])
 for number,source in enumerate(sources):
  path=directory/source['file'];source_dir=directory/source['id'];source_dir.mkdir(exist_ok=True)
  event('analyze',f'分析素材 {number+1}/{len(sources)}：识别镜头与语音')
  audio=source_dir/'audio.wav'
  if source['has_audio']:execute([ffmpeg_binary(),'-v','error','-nostdin','-y','-threads','2','-protocol_whitelist','file,pipe','-i',str(path),'-vn','-ar','16000','-ac','1',str(audio)],90)
  report=source_dir/'analysis.json'
  if not report.exists():execute([str(python),str(ROOT/'scripts/analyze_edit_media.py'),str(path),str(audio) if source['has_audio'] else '-',str(report),'--model',str(model),'--duration',str(source['duration']),'--context',record['prompt'][:300]],max(900,int(source['duration']*2)))
  analysis=json.loads(report.read_text());source['transcript']=analysis['transcript']
  # Sample each scene, then distribute extra observations across long scenes.
  positions=[]
  for scene in analysis['scenes']:
   positions.extend([scene['start']+(scene['end']-scene['start'])*f for f in ([.2,.6,.85] if scene['end']-scene['start']>20 else [.5])])
  # Livestreams/gameplay may be one continuous scene: inspect evenly through it,
  # not only three arbitrary frames, so later demonstrations are not invisible.
  limit=36 if record['mode']=='product' else 24
  count=min(limit,max(3,math.ceil(source['duration']/10)))
  positions+= [(i+.5)*source['duration']/count for i in range(count)]
  positions=sorted(set(round(t,2) for t in positions if 0<=t<source['duration']))
  if len(positions)>limit:positions=[positions[round(i*(len(positions)-1)/(limit-1))] for i in range(limit)]
  cached_observations=source_dir/f'observations-v{EDITING_VERSION}-{record["mode"]}.json'
  if cached_observations.exists():local_observations=json.loads(cached_observations.read_text())
  else:
   local_observations=[]
   for n in range(0,len(positions),6):
    batch=positions[n:n+6];images=[]
    for j,at in enumerate(batch):
     image=source_dir/f'frame-{n+j}.jpg';frame(path,image,at);images.append(image)
    prompt=observation_prompt(record['mode'],batch,record['prompt'])
    def check(value):
     if not isinstance(value.get('observations'),list) or len(value['observations'])!=len(batch):raise ValueError('每张图需要一条观察记录。')
     for item,at in zip(value['observations'],batch):
      if not isinstance(item,dict) or isinstance(item.get('time'),bool) or not math.isfinite(float(item.get('time',-1))) or abs(float(item.get('time',-1))-at)>.1 or not isinstance(item.get('description'),str) or not item['description'].strip() or not isinstance(item.get('highlight'),int) or isinstance(item['highlight'],bool) or not 0<=item['highlight']<=5:raise ValueError('观察记录需包含对应时间、实际描述与0至5整数评分。')
    result=vision.json(prompt,check,attempts=2,images=images)
    local_observations.extend({**item,'source_id':source['id']} for item in result['observations'])
   write_json(cached_observations,local_observations)
  observations.extend(local_observations)
  # Audio energy is supporting evidence, never the sole criterion for highlights.
  if audio.exists():
   import numpy as np
   with wave.open(str(audio)) as wav:pcm=np.frombuffer(wav.readframes(wav.getnframes()),dtype=np.int16).astype(float);rate=wav.getframerate()
   energy=[{'time':i,'rms':round(float(np.sqrt(np.mean(pcm[i*rate:(i+1)*rate]**2))),1)} for i in range(int(source['duration'])) if len(pcm[i*rate:(i+1)*rate])]
   source['audio_peaks']=sorted(energy,key=lambda x:x['rms'],reverse=True)[:8]
  source['scenes']=analysis['scenes']
 event('planning','根据真实画面、语音和目标时长编排精剪方案')
 evidence=[{k:s.get(k) for k in ['id','name','duration','transcript','scenes','audio_peaks']} for s in sources]
 prompt=planning_prompt(record['mode'],record['target_duration'],record['prompt'],evidence,observations)
 write_json(directory/'observations.json',observations)
 validate=lambda v:budget_plan(v,sources,record['target_duration'],record['mode'])
 plan=validate(text.json(prompt,validate,attempts=3))
 for attempt in range(2):
  plan['subtitles']=selected_subtitles(plan,sources)
  event('review','按'+MODES[record['mode']]['title']+'模板核对选段、上下文与叙事完整性')
  review=review_edit(directory,sources,plan,text,record['mode'])
  if review['passed']:break
  if attempt==1:raise ValueError('剪辑方案未通过内容核对：'+'；'.join(review['issues'])[:240]+'。请补充明确要求后重试。')
  event('planning','根据质检意见调整选段，保留完整原声')
  correction=prompt+'\n上次方案：'+json.dumps(plan,ensure_ascii=False)+'\n必须修复以下问题后返回完整方案：'+json.dumps(review['issues'],ensure_ascii=False)
  plan=validate(text.json(correction,validate,attempts=2))
 plan['quality']={'template_version':EDITING_VERSION,'passed':True,'notes':review.get('notes','')[:400]}
 write_json(directory/'observations.json',observations)
 return sources,plan

def selected_subtitles(plan,sources):
 subtitles=[];output_time=0;known={s['id']:s for s in sources}
 for clip in plan['clips']:
  for cue in known[clip['source_id']].get('transcript',[]):
   start=max(cue['start'],clip['start']);end=min(cue['end'],clip['end'])
   if end-start>.1 and cue['start']>=clip['start']-.2 and cue['end']<=clip['end']+.2:
    subtitles.append({'start':round(output_time+start-clip['start'],3),'end':round(output_time+end-clip['start'],3),'text':cue['text']})
  output_time+=clip['end']-clip['start']
 return subtitles

def review_edit(directory,sources,plan,gateway,mode):
 directory=Path(directory)
 evidence=[{k:s.get(k) for k in ['id','name','transcript']} for s in sources]
 selected=[]
 for index,clip in enumerate(plan['clips'],1):
  source=next(s for s in sources if s['id']==clip['source_id'])
  cues=[c for c in source.get('transcript',[]) if min(c['end'],clip['end'])-max(c['start'],clip['start'])>.1]
  selected.append({'number':index,'clip':clip,'original_words':cues})
 if mode=='product' and not any(x['original_words'] for x in selected):
  raise ValueError('未识别到清楚的商品讲解，无法核对带货内容。请上传包含清晰原声的直播片段。')
 observations=json.loads((directory/'observations.json').read_text()) if (directory/'observations.json').is_file() else []
 # Include edited captions so changes to names/numbers invalidate the review.
 fingerprint=hashlib.sha256(json.dumps({'version':EDITING_VERSION,'contract':TEMPLATES[mode],'mode':mode,'evidence':evidence,'selected':selected,'observations':observations,'subtitles':plan.get('subtitles')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 cached=directory/'edit_quality.json'
 if cached.is_file():
  prior=json.loads(cached.read_text())
  if prior.get('fingerprint')==fingerprint and prior.get('passed') is True:return prior
 prompt=review_prompt(mode,evidence,selected,observations)
 if 'subtitles' in plan:prompt+='\n当前成片字幕：'+json.dumps(plan['subtitles'],ensure_ascii=False)
 def check(value):
  if not isinstance(value.get('passed'),bool) or not isinstance(value.get('issues'),list) or len(value['issues'])>12 or any(not isinstance(x,str) or not x.strip() or len(x)>600 for x in value['issues']):raise ValueError('请返回明确质检结果与最多12条具体问题。')
  if value['passed']!= (not value['issues']):raise ValueError('通过时问题必须为空，不通过时须给出具体问题。')
  if not isinstance(value.get('notes',''),str):raise ValueError('核对说明应为文字。')
 review=gateway.json(prompt,check,attempts=2)
 review.update(fingerprint=fingerprint,template_version=EDITING_VERSION)
 write_json(cached,review)
 if mode=='product':write_json(directory/'commerce_review.json',review)
 return review

def review_commerce(directory,sources,plan,gateway):
 return review_edit(directory,sources,plan,gateway,'product')


def render(directory,record,plan,event):
 directory=Path(directory);sources={x['id']:x for x in record['sources']};parts=[];subtitles=[];output_time=0
 orientation=record.get('orientation','landscape');width,height=(1080,1920) if orientation=='portrait' else (1920,1080)
 for i,clip in enumerate(plan['clips']):
  event('render',f'正在导出片段 {i+1}/{len(plan["clips"])}')
  source=sources[clip['source_id']];duration=clip['end']-clip['start'];part=directory/f'part-{i:02}.mp4'
  # Preserve the whole source (especially game HUD); focus is a subtle inset settle,
  # never a destructive crop of source content.
  scale=f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x10141d,setsar=1,fps=30'
  if clip['effect']=='focus':
   inner_w=2*int(width*.96/2);inner_h=2*int(height*.96/2)
   scale=f"scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x10141d,setsar=1,fps=30,zoompan=z='1+0.04*min(on/15,1)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=30"
  args=[ffmpeg_binary(),'-v','error','-nostdin','-y','-threads','2','-ss',str(clip['start']),'-protocol_whitelist','file,pipe','-i',str(directory/source['file'])]
  if not source['has_audio']:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
  args+=['-t',str(duration),'-map','0:v:0','-map','0:a:0' if source['has_audio'] else '1:a:0','-vf',scale,'-af',f'aresample=48000,apad,afade=t=in:d=0.015,afade=t=out:st={max(0,duration-.02)}:d=0.02','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-threads','2','-filter_threads','1','-c:a','aac','-ar','48000','-ac','2','-b:a','160k','-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(part)]
  execute(args,300);parts.append(part)
  for cue in source.get('transcript',[]):
   start=max(cue['start'],clip['start']);end=min(cue['end'],clip['end'])
   if end-start>.1:
    # Do not pretend partially cut spoken phrases are complete subtitles.
    if cue['start']<clip['start']-.2 or cue['end']>clip['end']+.2:continue
    subtitles.append({'start':output_time+start-clip['start'],'end':output_time+end-clip['start'],'text':cue['text']})
  output_time+=duration
 listing=directory/'parts.txt';listing.write_text('\n'.join("file '"+p.name+"'" for p in parts))
 joined=directory/'joined.mp4';event('compose','合并片段与字幕，检查成片')
 execute([ffmpeg_binary(),'-v','error','-nostdin','-y','-protocol_whitelist','file,pipe','-f','concat','-safe','1','-i',str(listing),'-c','copy','-movflags','+faststart',str(joined)],120)
 if 'subtitles' in plan:subtitles=plan['subtitles']
 srt=directory/'subtitles.srt';write_subtitles([{'duration':output_time,'narration':'','subtitles':subtitles}],srt)
 final=directory/'final.mp4'
 args=[ffmpeg_binary(),'-v','error','-nostdin','-y','-threads','2','-i',str(joined)]
 if subtitles and record.get('captions',True):
  # Use a fixed safe filename with cwd; no model text enters filter syntax.
  args+=['-vf',"subtitles=subtitles.srt:force_style='FontName=Noto Sans CJK SC,FontSize=18,Outline=1.2,Shadow=0,MarginV=30,Alignment=2'",'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-threads','2','-filter_threads','1']
 else:args+=['-c:v','copy']
 args+=['-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','192k','-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(final)]
 run_command(args,timeout=600,cwd=directory)
 actual=inspect_media(final)
 if abs(actual['duration']-output_time)>.5:raise ValueError('成片时长检查未通过，请重试导出。')
 execute([ffmpeg_binary(),'-v','error','-nostdin','-threads','2','-filter_threads','1','-i',str(final),'-f','null','-'],180)
 frame(final,directory/'poster.jpg',actual['duration']*.4)
 write_json(directory/'timeline.json',{'version':1,'fps':30,'sources':[{k:s[k] for k in ['id','name','duration']} for s in record['sources']],**plan})
 execute([str(ROOT/'.venv-editing/bin/python'),str(ROOT/'scripts/export_edit_timeline.py'),str(directory/'timeline.json'),str(directory/'timeline.otio')],30)
 return actual
