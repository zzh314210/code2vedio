"""Full orchestration: reject final, repair only code, rerender, re-review, release."""
import copy,json,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from pipeline import VideoPipeline
from configuration import merge,DEFAULTS
from media import ffmpeg_binary
from quality_harness import QualityBudget,QualityBudgetExceeded,QualityRejected,verify_release

class Gateway:
 client=None
 def __init__(self,settings,role='text',**kw):self.settings=settings;self.role=role;self.usage={};self.finals=0
 def json(self,prompt,validator=None,**kw):
  if getattr(self,'budget',None):self.budget.take_call(self.role,self.settings.get('usage_stage','prepare'),'fixture')
  if self.role=='acceptance':value={'checks':[{'id':'specific_'+cat,'beat_id':'section_1:1','category':cat,'requirement':'展示甲乙效率相加为每日完成六分之一工程'} for cat in ('content','visual')]}
  elif self.role=='vision':
   ctx=json.loads(prompt[prompt.index('{"frozen_checks"'):]);self.finals+=ctx['scope']=='final'
   value={'checks':[{'id':c['id'],'status':'fail' if ctx['scope']=='final' and self.finals==1 else 'pass','frame_ids':[x['id'] for x in ctx['frames'] if x['beat_id']==c['beat_id']],'detail':'合成字幕遮住图示，需要把图示上移' if ctx['scope']=='final' and self.finals==1 else '数值、图示与旁白一致，空间清晰，没有遮挡'} for c in ctx['frozen_checks']]}
  else:value={'beats':[{'code':'self.wait(0.2)'}]}
  if validator:validator(value)
  return value

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as td:
 project=Path(td)/'project';channel={'protocol':'chat_completions','base_url':'https://example.org/v1','api_key':'fixture','model':'fixture'}
 c=merge(DEFAULTS,{'style':'studio_editorial','text':channel,'acceptance':channel,'vision':{**channel,'enabled':True,'inherit_text':False,'require_pass':True},'tts':{'provider':'none'},'teaching_research':{'enabled':False},'quality':{'enabled':True,'max_model_calls':20,'final_revisions':1},'video':{'target_duration':15,'subtitle_mode':'burn'}})
 events=[];renders=[]
 def encode(args):subprocess.run([ffmpeg_binary(),'-y','-v','error',*args],check=True,capture_output=True,timeout=90)
 with patch('pipeline.ModelGateway',Gateway),patch('execution.manim_api_names',return_value=set()):
  p=VideoPipeline('甲乙两队合作的效率图解',c,project/'output',project=project,on_event=events.append)
  outline={'topic':'工程合作','target_audience':'初学者','warnings':[],'sections':[{'id':'section_1','title':'合作效率','goal':'理解效率相加','key_points':['每天完成六分之一'],'sources':[]}]}
  board={'sections':[{'id':'section_1','title':'合作效率','beats':[{'narration':'甲乙合作每天完成六分之一。','caption':'合作效率六分之一','visual':'两队的效率条相加，合成六分之一进度条。','duration_seconds':2}]}]}
  for name,value in [('outline',outline),('storyboard',board),('section_1_code',{'beats':[{'code':'self.wait(0.1)'}]})]:(p.output/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False))
  approved=(p.output/'storyboard.json').read_bytes()
  def audio(section):
   (p.output/'audio').mkdir(exist_ok=True);target=p.output/'speech.wav';encode(['-f','lavfi','-i','sine=frequency=440:duration=2',str(target)])
   for beat in section['beats']:beat.update(duration=2,audio=str(target),subtitles=[{'start':0,'end':2,'text':beat['narration']}])
   return section
  def render(section,snippets,revision):
   renders.append(copy.deepcopy(snippets));color='0x143348' if len(renders)==1 else '0x145548';target=p.output/'fixture-render.mp4';encode(['-f','lavfi','-i',f'color=c={color}:s=640x360:r=30:d=2','-c:v','libx264','-threads','2',str(target)]);return target
  p.prepare_audio=audio;p.render=render
  final=p.run();verify_release(p.output,final)
  assert len(renders)==2 and renders[0]!=renders[1],'failed film did not trigger code regeneration/render'
  assert (p.output/'storyboard.json').read_bytes()==approved,'approved storyboard changed'
  assert p.harness.budget.state['revisions']['final:film']==1
  assert p.vision.finals==2,'repaired film was not reviewed again'
  assert (p.output/'quality/acceptance.json').is_file() and not (p.output/'candidate.mp4').exists()
  assert any(e['stage']=='acceptance' and e['status']=='failed' for e in events)
  # Re-instantiation cannot reset the final repair allowance.
  b=QualityBudget(p.harness.directory,p.harness.policy)
  try:b.take_revision('final')
  except QualityBudgetExceeded:pass
  else:raise AssertionError('retry reset correction cap')
print('PASS: complete pipeline final rejection -> targeted code repair -> actual rerender/composition -> fresh final review -> release; approved planning preserved and retry cannot reset caps')
