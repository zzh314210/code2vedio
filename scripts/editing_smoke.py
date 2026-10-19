"""Real media export plus malformed/overlapping timeline rejection; no model calls."""
import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from editing import inspect_media,validate_clips,render,execute
from media import ffmpeg_binary
with tempfile.TemporaryDirectory() as d:
 root=Path(d)
 for name,color,audio in [('one','royalblue',True),('two','orange',False)]:
  args=[ffmpeg_binary(),'-v','error','-y','-f','lavfi','-i',f'color={color}:s=320x180:r=30:d=4']
  if audio:args+=['-f','lavfi','-i','sine=frequency=440:duration=4']
  args+=['-t','4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(root/(name+'.mp4'))];execute(args)
 sources=[{'id':'s'+str(i+1),'file':name+'.mp4','name':name+'.mp4',**inspect_media(root/(name+'.mp4')),'transcript':[{'start':.2,'end':1.5,'text':'声音与画面保持同步。'}] if i==0 else []} for i,name in enumerate(['one','two'])]
 plan=validate_clips({'clips':[{'source_id':'s1','start':0,'end':2,'effect':'focus'},{'source_id':'s2','start':1,'end':3,'effect':'none'}]},sources)
 for bad in [float('nan'),float('inf'),-1,8]:
  try:validate_clips({'clips':[{'source_id':'s1','start':bad,'end':3}]},sources)
  except ValueError:pass
  else:raise AssertionError('Invalid timeline accepted')
 for clips in [[{'source_id':'../../private','start':0,'end':2}],[{'source_id':'s1','start':0,'end':2},{'source_id':'s1','start':1,'end':3}],[{'source_id':'s1','start':0,'end':2,'effect':'evil shell command'}]]:
  try:validate_clips({'clips':clips},sources)
  except ValueError:pass
  else:raise AssertionError('Unsafe cut accepted')
 actual=render(root,{'sources':sources,'orientation':'landscape','captions':True},plan,lambda *_:None)
 assert abs(actual['duration']-4)<.1 and actual['width']==1920 and actual['height']==1080
 assert (root/'timeline.otio').is_file() and 'OTIO_SCHEMA' in (root/'timeline.otio').read_text()
 assert '声音与画面' in (root/'subtitles.srt').read_text()
 actual=render(root,{'sources':sources,'orientation':'portrait','captions':True},plan,lambda *_:None)
 assert abs(actual['duration']-4)<.1 and actual['width']==1080 and actual['height']==1920
 (root/'bad.mp4').write_text('#EXTM3U\nhttp://127.0.0.1/private\n')
 try:inspect_media(root/'bad.mp4')
 except (ValueError,RuntimeError):pass
 else:raise AssertionError('Playlist disguised as video accepted')
print('PASS: real mixed audio/silent clips, restrained focus, subtitles, 1080p duration, complete decode, OTIO export; nonfinite/unknown/overlap/effect/playlist rejection.')

from editing import budget_plan
s=[{'id':'s1','duration':120,'transcript':[]}]
raw={'clips':[{'source_id':'s1','start':a,'end':b,'priority':p,'required':r} for a,b,p,r in [(0,10,4,False),(12,25,2,False),(30,50,5,True),(60,75,1,False)]]}
plan=budget_plan(raw,s,30,'product');assert plan['duration']==30 and any(c['start']==30 for c in plan['clips'])
for seconds in [29,121]:
 try:validate_clips({'clips':[{'source_id':'s1','start':0,'end':seconds}]},[{'id':'s1','duration':150}],mode='product')
 except ValueError:pass
 else:raise AssertionError('Out-of-range commerce export accepted')
try:validate_clips({'clips':[{'source_id':'s1','start':2,'end':8}]},[{'id':'s1','duration':10,'transcript':[{'start':0,'end':4,'text':'完整条件'}]}],speech_safe=True)
except ValueError:pass
else:raise AssertionError('Half sentence accepted')
print('PASS: whole-clip duration budgeting retains required sales conditions; commerce output bounds and complete speech boundaries enforced.')
