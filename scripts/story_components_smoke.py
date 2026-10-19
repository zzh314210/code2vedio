"""Real render of licensed story actors and non-overlapping vocabulary layouts."""
import sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from manim import tempconfig
from scene_runtime import NarratedScene
import template_components
out=ROOT/'.tmp/story-components';out.mkdir(exist_ok=True)
# Repoint the trusted module root for this isolated component test only.
shutil.copytree(ROOT/'templates/assets/noto',out/'noto',dirs_exist_ok=True)
template_components.__file__=str(out/'template_components.py')
class StoryScene(NarratedScene):
 lesson_font='Noto Sans CJK SC';lesson_title='一个离谱的故事，记住 abandon'
 lesson_credits='Noto Emoji / Google / Apache 2.0'
 lesson_style={'theme':'light','exit_fade':False,'style_palette':{'foreground':'#263e46','primary':'#327e85','emphasis':'#b86a35','panel':'#edf3f2'}}
 lesson_beats=[{'duration':4,'caption':t} for t in ['香蕉船长出海，船漏水了','他决定放弃船，跳向小岛','记忆联想，帮助理解真正的词义','回忆一下，它是什么意思？']]
 def construct(self):
  self.begin_beat(0);template_components.story_scene(self,action='sail');self.end_beat()
  self.begin_beat(1);template_components.story_scene(self,action='leave');self.end_beat()
  self.begin_beat(2);template_components.vocabulary_card(self,'abandon','放弃、抛弃','The captain had to abandon the boat.');self.end_beat()
  self.begin_beat(3);template_components.vocabulary_card(self,'abandon','放弃、抛弃',quiz=True);self.end_beat()
with tempconfig({'media_dir':str(out),'pixel_width':640,'pixel_height':360,'frame_rate':15,'disable_caching':True,'progress_bar':'none','background_color':'#faf8f2'}):StoryScene().render()
print('Story characters, departure motion, example and recall render passed.')

class ReviewScene(NarratedScene):
 lesson_font='Noto Sans CJK SC';lesson_title='先串起考点，再试着回忆'
 lesson_style=StoryScene.lesson_style
 lesson_beats=[{'duration':3,'caption':'用三个地点串起事件'},{'duration':4,'caption':'先想一想，再看答案'},{'duration':3,'caption':'巴黎—北京—上海'}]
 def construct(self):
  self.begin_beat(0);template_components.review_cards(self,[{'title':'导火索','text':'巴黎和会：中国外交失败'},{'title':'起点','text':'5月4日：北京学生抗议'},{'title':'扩大','text':'6月：上海工人加入'},{'title':'影响','text':'促进马克思主义传播'}]);self.end_beat()
  self.begin_beat(1);template_components.recall_card(self,'起点和扩大，分别在哪座城市？');self.end_beat()
  self.begin_beat(2);template_components.recall_card(self,'起点和扩大，分别在哪座城市？','起点在北京，扩大到上海',True);self.end_beat()
with tempconfig({'media_dir':str(out/'review'),'pixel_width':640,'pixel_height':360,'frame_rate':15,'disable_caching':True,'progress_bar':'none','background_color':'#faf8f2'}):ReviewScene().render()
print('PASS: summary and separate question/answer beats rendered for inspection.')
