"""Render real maps and knowledge nodes in both aspect ratios with trusted runtime."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from manim import tempconfig
from scene_runtime import NarratedScene
from template_components import map_story,knowledge_map,media_shot
OUT=ROOT/'.tmp/component-review';OUT.mkdir(exist_ok=True)
for portrait in [False,True]:
 class TemplateScene(NarratedScene):
  lesson_title='空间、关系与真实素材'
  lesson_font='Noto Sans CJK SC'
  lesson_style={'theme':'light','exit_fade':False,'orientation':'portrait' if portrait else 'landscape','style_palette':{'foreground':'#263e46','primary':'#327e85','emphasis':'#b86a35','panel':'#edf3f2'}}
  lesson_assets={'demo':str(ROOT/'templates/assets/frame-brief.png')}
  lesson_beats=[{'duration':3,'caption':c} for c in ['巴黎、北京与上海：真实地点，叙事关联','从导数到单调性，再到极值','真实产品截图，不虚构界面']]
  def construct(self):
   self.begin_beat(0);map_story(self,[{'name':'巴黎','lat':48.86,'lon':2.35},{'name':'北京','lat':39.90,'lon':116.41},{'name':'上海','lat':31.23,'lon':121.47}],2,date='1919年6月',event='工人参与，运动扩大');self.end_beat()
   self.begin_beat(1);knowledge_map(self,['导数','单调性','极值','常见误区','回忆检验'],2);self.end_beat()
   self.begin_beat(2);media_shot(self,'demo','输入需求，让想法清楚呈现');self.end_beat()
 name='portrait' if portrait else 'landscape'
 with tempconfig({'media_dir':str(OUT/name),'pixel_width':360 if portrait else 640,'pixel_height':640 if portrait else 360,'frame_width':8 if portrait else 14.2222222222,'frame_height':14.2222222222 if portrait else 8,'frame_rate':15,'disable_caching':True,'progress_bar':'none','background_color':'#faf8f2'}):TemplateScene().render()
print('Rendered both aspect ratios for map / framework / product inspection.')
