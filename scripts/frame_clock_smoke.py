"""Render fractional beat lengths and ensure speech/frame clocks do not drift."""
import sys,tempfile,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from manim import tempconfig,Dot,FadeIn,RIGHT
from scene_runtime import NarratedScene
class ClockScene(NarratedScene):
 lesson_font='Noto Sans CJK SC'
 lesson_title='帧与配音同步'
 lesson_style={'exit_fade':False}
 lesson_beats=[{'duration':n/30,'caption':'同步检查'} for n in [31,38,47,32,41,35]]
 def construct(self):
  for i in range(len(self.lesson_beats)):
   self.begin_beat(i);d=Dot();self.play(FadeIn(d),run_time=.13);self.play(d.animate.shift(RIGHT),run_time=.37);self.wait(.11);self.end_beat()
with tempfile.TemporaryDirectory() as d,tempconfig({'media_dir':d,'pixel_width':320,'pixel_height':180,'frame_rate':30,'disable_caching':True,'progress_bar':'none'}):
 scene=ClockScene();scene.render();path=next(Path(d).rglob('ClockScene.mp4'))
 data=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','json',str(path)]))
 actual=int(data['streams'][0]['nb_frames']);expected=sum([31,38,47,32,41,35]);assert actual==expected,(actual,expected)
print('PASS: fractional animations across six beats render exactly 224 frames, without accumulated narration drift.')
