"""Quality boundaries: frozen approval, evidence, durable budgets, delivery, real media."""
import copy,json,sys,tempfile,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from quality_harness import QualityHarness,QualityBudget,QualityBudgetExceeded,QualityRejected,digest,file_hash,verify_release
from media import ffmpeg_binary,mux,probe
from model_gateway import ModelGateway
from subtitle_render import wrap_caption

class Criteria:
 def __init__(self):self.calls=0
 def json(self,prompt,validator,**kw):
  self.calls+=1
  value={'checks':[{'id':'specific_'+g,'beat_id':'section_1:1','category':g,'requirement':'清楚显示甲乙合作每天完成六分之一工程量'} for g in ('content','visual')]};validator(value);return value
class Vision:
 def __init__(self,mode='pass'):self.mode=mode;self.calls=0
 def json(self,prompt,validator,images=None):
  self.calls+=1;ctx=json.loads(prompt[prompt.index('{"frozen_checks"'):]);bid=ctx['frozen_checks'][0]['beat_id'];refs=[f['id'] for f in ctx['frames'] if f['beat_id']==bid]
  rows=[dict(id=c['id'],status='pass' if self.mode=='fabricate' else self.mode,frame_ids=['invented'] if self.mode=='fabricate' else refs,detail='画面显示两队效率汇合，标注六分之一，与要求一致') for c in ctx['frozen_checks']]
  if self.mode=='omit':rows=[]
  value={'checks':rows};validator(value);return value

def rejects(fn,exception=Exception):
 try:fn()
 except exception:return
 raise AssertionError('unsafe result accepted')

with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as td:
 d=Path(td);p=SimpleNamespace(output=d,config={'quality':{'max_model_calls':2,'final_revisions':0},'video':{'subtitle_mode':'off'}},event=lambda *a:None,acceptance=Criteria(),vision=Vision())
 h=QualityHarness(p);p.harness=h
 outline={'topic':'合作工程'};board={'sections':[{'id':'section_1','beats':[{'narration':'合效是六分之一。','visual':'甲乙效率合并为六分之一','duration':4,'subtitles':[{'start':.1,'end':3.8,'text':'合效是六分之一。'}]}]}]}
 canonical=copy.deepcopy(board);contract=h.ensure_contract(outline,board);h.ensure_contract(outline,board);assert p.acceptance.calls==1
 assert {c['category'] for c in contract['checks']}=={'content','visual','coherence'}
 h.timeline_check(board)
 bad=copy.deepcopy(board);bad['sections'][0]['beats'][0]['subtitles'][0]['text']='缺失文稿';rejects(lambda:h.timeline_check(bad),QualityRejected)
 bad=copy.deepcopy(board);bad['sections'][0]['beats'][0]['subtitles'][0]['end']=20;rejects(lambda:h.timeline_check(bad),QualityRejected)
 long_board={'sections':[{'id':f'section_{n}','beats':[{'duration':10} for _ in range(6)]} for n in range(3)]}
 h.policy['sample_seconds']=.5;assert 360<=len(h.positions(long_board,180))<=960;h.policy['sample_seconds']=2
 pos=h.positions(board,4);assert len(pos)>=3 and min(pos)>=0 and max(pos)<4
 from concurrent.futures import ThreadPoolExecutor
 # Separate instances simulate independent callers sharing one persistent cap.
 concurrent_dir=d/'concurrent'
 def attempt(n):
  try:QualityBudget(concurrent_dir,{'max_model_calls':2}).take_call('text','code',str(n));return True
  except QualityBudgetExceeded:return False
 with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(attempt,range(12)))==2
 h.budget.take_call('text','code','primary');QualityBudget(h.directory,h.policy).take_call('vision','review','fallback');rejects(lambda:h.budget.take_call('text','code','third'),QualityBudgetExceeded);rejects(lambda:h.budget.take_revision('final'),QualityBudgetExceeded)
 # Actual image positions; the model cannot pass missing or fabricated evidence.
 video=d/'mock.mp4';video.write_bytes(b'identity1');frames=[d/f'f{i}.jpg' for i in pos]
 for f in frames:f.write_bytes(b'test-image')
 with patch('quality_harness.probe',return_value={'duration':4}),patch('quality_harness.sample_frames',return_value=frames):
  for mode in ('fabricate','omit'):
   p.vision=Vision(mode);rejects(lambda:h.review_video(video,board,mode),ValueError)
  p.vision=Vision('uncertain');assert not h.review_video(video,board,'uncertain')['passed']
  p.vision=Vision();part=h.review_video(video,board,'section_1');assert part['passed']
  final=h.review_video(video,board,'final');assert final['passed'];calls=p.vision.calls
  assert h.review_video(video,board,'final')['passed'] and p.vision.calls==calls
  # A changed media hash always invalidates the review cache.
  video.write_bytes(b'identity2');h.review_video(video,board,'final');assert p.vision.calls>calls
  video.write_bytes(b'identity1')
 host={'passed':True,'checks':[{'id':k,'status':'pass'} for k in ('streams','duration','decode','blank','silence','subtitles')],'media_sha256':file_hash(video)}
 assert not h.report(host,final)['passed'],'parts are mandatory'
 result=h.report(host,final,[{'section_id':'section_1','passed':True,'media_sha256':part['media_sha256']}]);assert result['passed']
 for name,value in [('outline',outline),('storyboard',canonical),('manifest',{'config':{'quality':{'enabled':True}}})]:(d/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False))
 verify_release(d,video);video.write_bytes(b'other film');rejects(lambda:verify_release(d,video),ValueError);video.write_bytes(b'identity1')
 # Unapproved changes cannot reuse a passing report.
 (d/'storyboard.json').write_text(json.dumps(bad));rejects(lambda:verify_release(d,video),ValueError)
 # Full decode + black/white + silence, independent of a model saying pass.
 ff=ffmpeg_binary();sound=d/'speech.wav'
 def run(args):subprocess.run([ff,'-hide_banner','-loglevel','error','-y',*args],check=True,capture_output=True,timeout=90)
 run(['-f','lavfi','-i','sine=frequency=440:duration=4','-c:a','pcm_s16le',str(sound)])
 for color in ('black','white','0x143348'):
  raw=d/(color+'.mp4');run(['-f','lavfi','-i',f'color=c={color}:s=640x360:r=15:d=4','-c:v','libx264','-threads','2',str(raw)])
  out=d/(color+'-mux.mp4');srt=d/'captions.srt';srt.write_text('1\n00:00:00,100 --> 00:00:03,800\n合效是六分之一。\n')
  mux(raw,sound,srt,out,4,subtitle_mode='off');technical=h.final_checks(out,board,sound)
  assert technical['passed']==(color=='0x143348'),technical
 run(['-f','lavfi','-i','anullsrc=r=48000:cl=mono','-t','4',str(sound)])
 assert not h.final_checks(out,board,sound)['passed']
 # Burned captions must exist in the lower screen; off has no subtitle track.
 run(['-f','lavfi','-i','sine=frequency=440:duration=4',str(sound)])
 burn=d/'burn.mp4';mux(raw,sound,srt,burn,4,subtitle_mode='burn');assert 'subtitle' in {s['type'] for s in probe(burn)['streams']}
 assert 'subtitle' not in {s['type'] for s in probe(out)['streams']}
 from PIL import Image,ImageChops
 shots=[]
 for path in (burn,out):
  pic=path.with_suffix('.png');run(['-ss','1','-i',str(path),'-frames:v','1',str(pic)]);shots.append(Image.open(pic).convert('RGB'))
 difference=ImageChops.difference(*shots);assert difference.crop((0,260,640,360)).getbbox(),'captions absent in lower safe area'
 assert not difference.crop((0,0,640,200)).getbbox(),'captions changed upper content'
 assert '{' not in ''.join(wrap_caption('{\\pos(1,1)}攻击',40))
print('PASS: frozen per-beat criteria, full transcript, invented evidence rejected, uncertain blocks, all-parts/final release, stale-media/plan rejection, durable hard bounds, actual black/white/silence and optional lower-screen captions')
