"""Targeted speech repair preserves the visual plan and fails closed on bad output."""
import copy,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from pipeline import VideoPipeline,NarrationBudgetError
from model_gateway import StructuredOutputError
outline={'sections':[{'id':'section_1'}]}
source={'sections':[{'id':'section_1','title':'导数','beats':[
 {'narration':'观察同一条曲线上的两个点，连接两个点就可以得到割线，接下来我们再慢慢移动其中一个点。','caption':'割线与两点','visual':'两个点连线，坐标保持准确'},
 {'narration':'随着间隔不断缩小，割线逐渐趋向切线。注意极限过程不是直接把分母取零，这一点特别重要。','caption':'割线趋近切线','visual':'动点接近，显示割线旋转'},
 {'narration':'现在请你回忆这段视频中给出的例子，横坐标为一时，平方函数的切线斜率到底等于多少？','caption':'想一想','visual':'只显示问题','recall_role':'question','hold_after_seconds':2},
 {'narration':'答案是二。因为这里的割线斜率等于二加间隔，当间隔趋近零，它的极限就是二。','caption':'斜率为2','visual':'揭晓并高亮切线','recall_role':'answer'}]}]}
short=['连起曲线上两点，得到割线。','间隔趋近零时，割线趋向切线；不能把分母直接取零。','平方函数在横坐标一处，切线斜率是多少？','答案是二。']
for mode in ['success','wrong_count','overlong','invalid_structure']:
 with tempfile.TemporaryDirectory() as temp:
  p=VideoPipeline.__new__(VideoPipeline);p.output=Path(temp);p.reference_images=[];p.config={'task':{'template_id':'math_visual','template_version':4},'video':{'target_duration':30,'max_beats':6}}
  def validate(value):p.validate_storyboard(value,outline)
  try:validate(source)
  except NarrationBudgetError:pass
  else:raise AssertionError('Fixture must exceed budget')
  class Gateway:
   def __init__(self):self.calls=0
   def json(self,prompt,validator,**kwargs):
    self.calls+=1
    if self.calls==1:raise StructuredOutputError('unusable',source,ValueError('bad schema') if mode=='invalid_structure' else NarrationBudgetError('too long'))
    assert kwargs['attempts']==2
    lines=short[:-1] if mode=='wrong_count' else [b['narration'] for b in source['sections'][0]['beats']] if mode=='overlong' else short
    result={'narrations':lines};validator(result);return result
  p.text=Gateway()
  before=copy.deepcopy(source)
  try:result=p.cached_json('storyboard.json','full storyboard',validate)
  except ValueError:
   assert mode!='success';assert not (p.output/'storyboard.json').exists()
  else:
   assert mode=='success';validate(result)
   for original,new in zip(source['sections'][0]['beats'],result['sections'][0]['beats']):
    assert {k:v for k,v in new.items() if k!='narration'}=={k:v for k,v in original.items() if k!='narration'}
   assert json.loads((p.output/'storyboard.json').read_text())==result
  assert source==before,'Repair mutated archived model response'
  if mode=='invalid_structure':assert p.text.calls==1,'Invalid schema must not use speech repair'
print('PASS: speech-only compression preserves visual facts/recall timing; wrong counts, overlong narration and structural failures remain blocked.')
