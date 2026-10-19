"""Render the real graph helper in both layouts and check numerical truth/bounds."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from manim import tempconfig
from scene_runtime import NarratedScene
from template_components import function_plot
out=ROOT/'.tmp/function-review';out.mkdir(exist_ok=True)
for portrait in [False,True]:
 class Demo(NarratedScene):
  lesson_font='Noto Sans CJK SC';lesson_title='导数：从割线走向切线'
  lesson_style={'theme':'light','orientation':'portrait' if portrait else 'landscape','exit_fade':False,'style_palette':{'foreground':'#283A44','primary':'#196CA5','emphasis':'#C56127','muted':'#526570','panel':'#F0EADB'}}
  lesson_beats=[{'duration':8,'caption':'点沿曲线接近，割线斜率趋近2'}]
  def construct(self):
   self.begin_beat(0)
   result=function_plot(self,mode='tangent',label='从平均变化到瞬时变化')
   assert np.allclose(result['secant_slopes'],[3,2.5,2.1])
   assert result['tangent_slope']==2
   axes=result['axes']
   for segment in result['curve_segments']:
    for point in segment.get_points():
     x,y=axes.p2c(point);assert -.501<=x<=2.501 and -.501<=y<=5.001,(x,y)
   self.end_beat()
 with tempconfig({'media_dir':str(out/('portrait' if portrait else 'landscape')),'pixel_width':360 if portrait else 640,'pixel_height':640 if portrait else 360,'frame_width':8 if portrait else 14.2222222222,'frame_height':14.2222222222 if portrait else 8,'frame_rate':15,'disable_caching':True,'progress_bar':'none','background_color':'#FBF7EE'}):Demo().render()
print('PASS: real polynomial movement/tangent, exact secant values, clipped curve points, landscape and portrait renders.')
