"""Semantic review cannot silently reuse a verdict after cuts/captions change."""
import copy, json, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from editing import review_edit, validate_clips, budget_plan

class Gateway:
    calls=0
    def json(self,prompt,check,attempts):
        self.calls+=1
        result={'passed':True,'issues':[],'notes':'完整语句与相同商品条件。'}
        check(result)
        return result

sources=[{'id':'s1','duration':60,'name':'original.mp4','transcript':[
    {'start':0,'end':10,'text':'完整的原声介绍。'},
    {'start':10,'end':30,'text':'适用条件与限制。'},
]}]
plan={'clips':[{'source_id':'s1','start':0,'end':30,'effect':'none'}],
      'subtitles':[{'start':0,'end':10,'text':'完整的原声介绍。'}]}
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);gateway=Gateway()
    review_edit(root,sources,plan,gateway,'product')
    review_edit(root,sources,copy.deepcopy(plan),gateway,'product')
    assert gateway.calls==1
    plan['subtitles'][0]['text']='改动商品数字。'
    review_edit(root,sources,plan,gateway,'product');assert gateway.calls==2
    plan['clips'][0]['end']=40
    review_edit(root,sources,plan,gateway,'product');assert gateway.calls==3
    review_edit(root,sources,plan,gateway,'highlights');assert gateway.calls==4
    (root/'observations.json').write_text(json.dumps([{'time':20,'description':'不同商品'}]))
    review_edit(root,sources,plan,gateway,'highlights');assert gateway.calls==5
for mode in ['highlights','product','gaming','documentary']:
    try:validate_clips({'clips':[{'source_id':'s1','start':5,'end':40}]},sources,mode=mode,speech_safe=True)
    except ValueError:pass
    else:raise AssertionError('Cut inside speech accepted: '+mode)
try:validate_clips({'clips':[{'source_id':'s1','start':0,'end':30,'effect':'focus'}]},sources,mode='documentary')
except ValueError:pass
else:raise AssertionError('Documentary accepted forbidden focus effect')
short={'clips':[{'source_id':'s1','start':0,'end':10}]}
try:budget_plan(short,sources,30,'highlights')
except ValueError:pass
else:raise AssertionError('Short plan without explanation silently accepted')
short['shorter_reason']='后半段全部是与主题无关的候场，只保留完整介绍。'
accepted=budget_plan(short,sources,30,'highlights')
assert accepted['duration']==10 and '目标30秒' in accepted['summary']
try:budget_plan(short,sources,30,'product')
except ValueError:pass
else:raise AssertionError('Commerce minimum bypassed by shortfall explanation')
try:validate_clips({'clips':[{'source_id':'s1','start':30,'end':40},{'source_id':'s1','start':0,'end':10}]},sources,mode='gaming')
except ValueError:pass
else:raise AssertionError('Game result shown before setup')
print('PASS: unchanged review cached; caption/cut/template/evidence changes reviewed again; complete speech and per-template effect limits.')
