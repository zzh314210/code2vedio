"""Adversarial proof and cross-stage checks, no paid API calls."""
import copy,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from logic_contract import solve,lesson_plan,validate_plan_handoff
from provider_protocols import reasoning_body
E='甲、乙、丙、丁四人中恰有一人做了这件事。甲说：是乙做的。乙说：不是我做的。丙说：不是甲做的。丁说：是丙做的。四人中只有一人说真话。'
C={'version':1,'people':list('甲乙丙丁'),'variable':{'id':'actor','label':'做事的人','values':list('甲乙丙丁')},'true_count':1,'assumptions':['四人中恰有一人做了这件事','四人中只有一人说真话'],'statements':[{'id':f's{i+1}','speaker':p,'text':t,'claim':cl} for i,(p,t,cl) in enumerate(zip('甲乙丙丁',['是乙做的','不是我做的','不是甲做的','是丙做的'],[{'eq':['actor','乙']},{'not':{'eq':['actor','乙']}},{'not':{'eq':['actor','甲']}},{'eq':['actor','丙']}]))]}
p=solve(C,E);assert p['answer']['actor']=='甲' and p['answer']['truth']==[False,True,False,False];assert [0,1] in p['contradiction_pairs']
o,b=lesson_plan(p);validate_plan_handoff(b,p,'storyboard')
for bad in [dict(C,true_count=2),dict(C,expected_actor='丁'),dict(C,assumptions=['题目没说的条件'])]:
 try:solve(bad,E)
 except ValueError:pass
 else:raise AssertionError('Invalid or nonunique problem accepted')
b['sections'][0]['beats'][4]['narration']='答案是丁'
try:validate_plan_handoff(b,p,'storyboard')
except ValueError:pass
else:raise AssertionError('Conflicting narration accepted')
for provider in ['compatible','dashscope','deepseek','moonshot','openai','anthropic','zhipu','doubao','minimax']:
 body,policy=reasoning_body({'provider':provider,'protocol':'anthropic' if provider=='anthropic' else 'chat_completions','model':'claude-opus-4-6','extra_body':{'enable_thinking':False}},24000)
 assert policy['enabled'] and policy['requested_effort']=='max'
 if provider in ('dashscope','compatible'):assert body['enable_thinking'] and body['reasoning_effort']=='max'
from logic_renderer import frame
beat=lesson_plan(p)[1]['sections'][0]['beats'][0]
frame(p,beat,0,3,15).save('/tmp/truth-layout.png')
print('PASS: finite truth table, contradiction proof, uniqueness rejection, exact narration handoff and nine provider policies')
# Public recalled examination: no hidden unique-offender assumption.
root=Path(__file__).resolve().parents[1]/'examples/truth_logic'
c=json.loads((root/'exam_contract.json').read_text());e=(root/'exam-question.md').read_text()
p=solve(c,e);assert p['answer']['option']=='A' and p['valid_worlds']==4
assert len(p['rows'])==16 and len(p['quantifier_sensitivity'])==4
assert all(x['entailed_options']==['A'] for x in p['quantifier_sensitivity'])
assert any(r['valid'] and r['world']['c'] for r in p['rows']),'Solver falsely assumes only A participated'
bad=copy.deepcopy(c);bad['statements'][3]['claim']={'eq':['d',True]}
try:solve(bad,e)
except ValueError:pass
else:raise AssertionError('Different truth relationship accepted by fixed proof template')
o,b=lesson_plan(p);validate_plan_handoff(o,p,'outline');validate_plan_handoff(b,p,'storyboard')
b['sections'][0]['beats'][2]['duration_seconds']=30;validate_plan_handoff(b,p,'storyboard')
o['sections'][0]['goal']='错误的新结论'
try:validate_plan_handoff(o,p,'outline')
except ValueError:pass
else:raise AssertionError('Proof-independent outline accepted')
print('PASS: real exam entailment across 16 worlds and quantifier variants, no unique-offender assumption, safe timing edits, outline tamper rejection')
