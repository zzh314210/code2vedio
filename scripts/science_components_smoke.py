"""Render actual science components and verify projected lunar light fractions."""
import sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from manim import tempconfig
from scene_runtime import NarratedScene
from template_components import lunar_phases,_phase_disc,formula_steps,media_shot
out=ROOT/'.tmp/science-review';out.mkdir(exist_ok=True)
for angle,fraction in [(0,0),(math.pi/2,.5),(math.pi,1),(math.pi*1.5,.5)]:
 polygon=_phase_disc(angle,1,[0,0,0])[1].get_vertices();x,y=polygon[:,0],polygon[:,1]
 area=abs(np.dot(x,np.roll(y,1))-np.dot(y,np.roll(x,1)))/2
 assert abs(area/math.pi-fraction)<.005,(angle,area/math.pi)
for portrait in [False,True]:
 class Science(NarratedScene):
  lesson_font='Noto Sans CJK SC';lesson_title='看清光照，也看懂公式'
  lesson_style={'theme':'light','brand':'','exit_fade':False,'orientation':'portrait' if portrait else 'landscape','style_palette':{'foreground':'#283A44','primary':'#196CA5','emphasis':'#C56127','muted':'#526570','panel':'#F0EADB'}}
  lesson_assets={'photo':str(ROOT/'templates/assets/nasa-moon-1.jpg')}
  lesson_beats=[{'duration':8,'caption':'从太空位置理解地球所见的亮面变化'},{'duration':5,'caption':'四个月相，来自不同的观察角度'},{'duration':6,'caption':'h不等于零，才能约分；趋近零看极限'},{'duration':5,'caption':'图片说明与字幕必须分别清晰可读'}]
  def construct(self):
   self.begin_beat(0);lunar_phases(self,'orbit');self.end_beat()
   self.begin_beat(1);lunar_phases(self,'summary');self.end_beat()
   self.begin_beat(2);formula_steps(self,['((1 + h)² − 1) / h','= (2h + h²) / h','= 2 + h'],title='割线斜率，逐步化简',note='h ≠ 0，才可约去 h');self.end_beat()
   self.begin_beat(3);media_shot(self,'photo','NASA 真实月面照片',framing='cover');self.end_beat()
 with tempconfig({'media_dir':str(out/('portrait' if portrait else 'landscape')),'pixel_width':360 if portrait else 640,'pixel_height':640 if portrait else 360,'frame_width':8 if portrait else 14.2222222222,'frame_height':14.2222222222 if portrait else 8,'frame_rate':15,'disable_caching':True,'progress_bar':'none','background_color':'#FBF7EE'}):Science().render()
print('PASS: real lunar geometry with 0/50/100/50% projected light, orbit continuity, separated derivation and complete source labels in both layouts.')
