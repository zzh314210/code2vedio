"""Build an original narrated sketch lesson using free TTS and isolated rendering."""
import json,sys,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from narration import Narrator
from media import probe,concat,fit_audio,write_subtitles,mux,ffmpeg_binary,run_command
from configuration import load_config
from execution import render_command
project=ROOT/'video_projects/studio-exam-sketch-demo'
output=project/'output';runtime=project/'code/runtime';output.mkdir(parents=True,exist_ok=True);runtime.mkdir(parents=True,exist_ok=True)
for name in ('handdrawn_runtime.py','handdrawn_bridge.cjs'):shutil.copy2(ROOT/'src'/name,runtime/name)
shutil.copytree(ROOT/'src/vendor',runtime/'vendor',dirs_exist_ok=True)
texts=[
'行测数量关系，牛吃草问题。草地匀速生长，二十四头牛六天吃完，二十一头牛八天吃完。换成十八头牛，需要多少天？先别套反比例，因为草每天都在长。',
'把一头牛一天的食量记作一份。六天吃掉一百四十四份，八天吃掉一百六十八份。多出的二十四份草，恰好是多长两天的量。所以，每天新长十二份。',
'十八头牛中，先让十二头牛吃掉当天新长的草。剩下六头牛，才真正消耗原有的存量。这就是净消耗：十八减十二，等于每天六份。',
'再回到二十四头牛的条件。它们每天净消耗十二份，六天正好吃完原有的草。因此，原有草量等于二十四减十二，再乘六，得到七十二份。',
'现在换成十八头牛。原有七十二份草，每天净消耗六份。七十二除以六，答案就是十二天，选B。注意，分母一定要扣掉每天新长的草。',
'总结三步：先用两组总量的差求增长，再用净消耗求原有存量，最后算时间。代回验证：二十一减十二等于九，七十二除以九，恰好八天。理解存量和增量，比死背公式更可靠。'
]
narrator=Narrator({'provider':'edge','voice':'zh-CN-YunxiNeural','rate':'-5%','timeout':90,'max_retries':2})
beats=[];audio=[]
for i,text in enumerate(texts):
 dest=output/f'narration-{i}.wav'
 if dest.is_file():info={'duration':probe(dest)['duration'],'subtitles':Narrator.fallback_subtitles(text,probe(dest)['duration'])}
 else:info=narrator.synthesize(text,dest)
 duration=info['duration']+1.4
 fitted=output/f'beat-{i}.wav';fit_audio(dest,fitted,duration)
 beats.append({'narration':text,'duration':duration,'subtitles':info.get('subtitles') or Narrator.fallback_subtitles(text,info['duration'])});audio.append(fitted)
 print('Narration',i+1,round(duration,2),'seconds',flush=True)
(output/'timeline.json').write_text(json.dumps(beats,ensure_ascii=False))
script=output/'exam_scene.py';shutil.copy2(ROOT/'deploy/sketch_exam_scene.py',script)
settings=load_config(ROOT/'config.local.json')['execution']
log=render_command([sys.executable,'-m','manim','-qh','--fps','30','--disable_caching','--media_dir',str(output/'media'),str(script),'ExamSketch'],project,output,settings,900)
(output/'render.log').write_text(log)
video=next((output/'media/videos').rglob('ExamSketch.mp4'))
concat(audio,output/'narration.wav',audio=True)
duration=write_subtitles(beats,output/'subtitles.srt')
mux(video,output/'narration.wav',output/'subtitles.srt',output/'final.mp4',duration)
run_command([ffmpeg_binary(),'-y','-ss',str(duration*.72),'-i',str(output/'final.mp4'),'-frames:v','1',str(output/'poster.jpg')])
print('COMPLETE',output/'final.mp4',probe(output/'final.mp4'),flush=True)
