"""Complete-canvas components must not receive extra overlapping model labels."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pipeline import VideoPipeline
p=VideoPipeline.__new__(VideoPipeline)
p.extensions={'map_story':{},'story_scene':{},'vocabulary_card':{},'media_shot':{},'knowledge_map':{},'function_plot':{},'formula_steps':{},'lunar_phases':{}}
for template,component in [('history_map','map_story'),('word_story','story_scene'),('word_story','vocabulary_card'),('product','media_shot'),('documentary','media_shot'),('notes','knowledge_map'),('notes','function_plot'),('math_visual','function_plot'),('math_visual','formula_steps'),('explainer','lunar_phases')]:
 p.config={'task':{'template_id':template},'video':{}}
 good=f'self.extension("{component}")\nself.wait(1)'
 p.validate_snippets({'beats':[{'code':good}]},1)
 for extra in ['\nx=self.scene_text("重复说明")\nself.add(x)',f'\nself.extension("{component}")']:
  try:p.validate_snippets({'beats':[{'code':good+extra}]},1)
  except ValueError:pass
  else:raise AssertionError('Overlapping template code accepted')
print('PASS: owned component layouts reject duplicate components and extra model-drawn labels.')

# Ordinary punctuation and an English brand must not make concise speech fail.
p.config={'task':{'template_id':'product'},'video':{'target_duration':30,'max_beats':6}}
outline={'sections':[{'id':'section_1'}]}
beat={'narration':'打开 Frame，写下一个想法。选择风格，看看画面预览。先修改大纲，再确认分镜，让每一步都更清楚。','caption':'从一个想法开始','visual':'真实界面截图'}
storyboard={'sections':[{'id':'section_1','title':'产品演示','beats':[beat]}]}
p.validate_storyboard(storyboard,outline)
storyboard['sections'][0]['beats']=[{**beat,'narration':'这段旁白重复讲述很多没有必要的细节。'*6} for _ in range(3)]
try:p.validate_storyboard(storyboard,outline)
except ValueError:pass
else:raise AssertionError('Overfull narration accepted')
print('PASS: concise mixed-language narration allowed, clearly overfull speech rejected before synthesis.')

from pipeline import validate_snippet
validate_snippet('orbit = DashedVMobject(Circle(radius=2))')
try:validate_snippet('orbit = DashedCircle(radius=2)')
except ValueError:pass
else:raise AssertionError('Invented Manim constructor accepted')
print('PASS: unknown Manim constructor rejected before rendering, valid dashed geometry allowed.')
validate_snippet("self.extension('function_plot', label='从割线到切线')", p.extensions)
try:validate_snippet("self.extension('function_plot', label="+repr('过长标题'*7)+")", p.extensions)
except ValueError:pass
else:raise AssertionError('Overlong graph label would waste a full render')
print('PASS: overlong literal graph labels rejected before rendering.')

p.config={'task':{'template_id':'word_story','template_version':4},'video':{'target_duration':60,'max_beats':6}}
base={'narration':'这是一个问题。','caption':'想一想','visual':'提问卡片'}
q={**base,'recall_role':'question','hold_after_seconds':2}
a={**base,'narration':'这是来自本课的答案。','recall_role':'answer'}
for sequence,valid in [([q],False),([q,a],True),([{**q,'hold_after_seconds':0},a],False)]:
 try:p.validate_storyboard({'sections':[{'id':'section_1','title':'回忆','beats':sequence}]},outline)
 except ValueError:assert not valid
 else:assert valid
print('PASS: current learning templates reserve a question, genuine recall pause, and following answer; missing answers rejected.')

p.config['task']={'template_id':'notes','template_version':5}
for sequence,valid in [([q,a],False),([q,a,q,a,q,a],True)]:
 try:p.validate_storyboard({'sections':[{'id':'section_1','title':'三道回忆小测','beats':sequence}]},outline)
 except ValueError:assert not valid
 else:assert valid
print('PASS: three promised recall questions require three real question/answer pairs.')
