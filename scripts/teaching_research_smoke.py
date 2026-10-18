"""Research must cite fetched text and retain ordered reasoning; never invent a fallback lesson."""
import copy
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import teaching_research as research
from teaching_library import TeachingSources
TEXT='先观察两个同时发生的变化。每头牛每天吃一份草。用牛吃草速度减去生长速度得到净消耗。原有草量等于每天净消耗乘以时间。'
SOURCES=[{'url':f'https://example.com/{i}','title':f'精讲{i}','text':TEXT+str(i)*500,'sha256':research.hashlib.sha256((TEXT+str(i)*500).encode()).hexdigest(),'segments':[{'start':0,'end':4,'text':'先观察两个同时发生的变化。'},{'start':4,'end':7,'text':'每头牛每天吃一份草。'},{'start':7,'end':11,'text':'用牛吃草速度减去生长速度得到净消耗。'},{'start':11,'end':14,'text':'原有草量等于每天净消耗乘以时间。'}]} for i in range(2)]
QUOTES=['先观察两个同时发生的变化。每头牛每天吃一份草。','用牛吃草速度减去生长速度得到净消耗。','原有草量等于每天净消耗乘以时间。']
PLAN={'primary_source_id':'WEB1','selection_reason':'同一完整方法','learner_start':'先理解每日变化','method':'净变化法','applicability':'匀速变化','steps':[{'id':f'T{i+1}','source_id':'WEB1','quote':q,'explanation':'原文同一步','why':'数量守恒','student_question':'为什么这样求','visual_action':'用流入流出抵消展示净消耗'} for i,q in enumerate(QUOTES)],'pitfalls':['不要把总量和速度混淆']}
class Gateway:
 def json(self,prompt,validator):
  value={'queries':['牛吃草 净变化 精讲','牛吃草 原理 解析']} if 'queries' in prompt[:400] else copy.deepcopy(PLAN)
  validator(value);return value

def search(self,query,platform='web',limit=8):return {'query':query,'results':[{'url':s['url'],'title':s['title']} for s in SOURCES]}
def ingest(self,url):return copy.deepcopy(next(s for s in SOURCES if s['url']==url))
with tempfile.TemporaryDirectory() as temp,patch.object(TeachingSources,'search',search),patch.object(TeachingSources,'ingest',ingest):
 settings={'library':str(Path(temp)/'library.db'),'platforms':[]}
 result=research.prepare_research('牛吃草 行测',{'context':''},settings,Path(temp)/'research',Gateway())
 assert result['plan']['steps'][0]['evidence_time']=={'start':0,'end':7}
 assert result['plan']['steps'][2]['evidence_time']=={'start':11,'end':14}
 assert research.prepare_research('牛吃草 行测',{'context':''},settings,Path(temp)/'research',Gateway())==result
 invalid=copy.deepcopy(result['plan']);invalid['steps'][0]['quote']='完全不存在于原文的所谓精华解题技巧'
 try:research.validate_plan(invalid,result['sources'])
 except ValueError:pass
 else:raise AssertionError('Invented evidence accepted')
 with patch.object(TeachingSources,'search',side_effect=RuntimeError('offline')):
  try:research.prepare_research('另一道行测题',{'context':''},settings,Path(temp)/'offline',Gateway())
  except RuntimeError:pass
  else:raise AssertionError('Offline research invented an explanation')
 assert (Path(temp)/'offline/retrieval.json').is_file()
 assert research.enabled_for('行测数量关系',{}) and not research.enabled_for('解释太阳系轨道',{})


assert research.enabled_for('用曲线解释复利', {'enabled':'auto','source_ids':['SRCexample']})
assert research.enabled_for('用曲线解释复利', {'enabled':'auto','reference_urls':['https://example.org/lesson']})
assert not research.enabled_for('讲解一道行测题', {'enabled':False,'source_ids':['SRCexample']})

print('PASS: retrieved evidence, exact-quote rejection, timestamp mapping, immutable research cache, no-source failure, topic/reference-sensitive activation.')
