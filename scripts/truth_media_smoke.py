"""Reject corrupt final-media handoffs without rendering or paid API calls."""
import copy,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import logic_contract as contract
from logic_acceptance import final_receipt

evidence=(ROOT/'examples/truth_logic/practice-question.md').read_text()
c=json.loads((ROOT/'examples/truth_logic/practice_contract.json').read_text())
proof=contract.solve(c,evidence);_,board=contract.lesson_plan(proof)
beats=[b for s in board['sections'] for b in s['beats']]
for b in beats:
 b['duration']=b['duration_seconds']
 b['subtitles']=[{'start':0,'end':b['duration'],'text':b['narration']}]
receipts=[{'engine':'logic_diagram','scenes':[{'scene_id':b['scene_id'],'proof_hash':proof['proof_hash'],'duration':b['duration'],'narration_sha256':contract.digest(b['narration'])} for b in beats]}]
details={'duration':sum(b['duration'] for b in beats),'streams':[{'type':t} for t in ('video','audio','subtitle')]}
with tempfile.TemporaryDirectory() as temp:
 final=Path(temp)/'final.mp4';final.write_bytes(b'media fixture; real films are separately decoded')
 good=final_receipt(proof,board,final,details,contract,receipts)
 assert good['scenes']==6 and len(good['final_sha256'])==64
 cases=[]
 r=copy.deepcopy(receipts);r[0]['scenes'].pop();cases.append((board,details,r))
 for key,value in [('proof_hash','wrong'),('narration_sha256','wrong'),('duration',999),('scene_id','wrong')]:
  r=copy.deepcopy(receipts);r[0]['scenes'][0][key]=value;cases.append((board,details,r))
 b=copy.deepcopy(board);b['sections'][0]['beats'][0]['subtitles']=[];cases.append((b,details,receipts))
 d=copy.deepcopy(details);d['streams']=[{'type':'video'},{'type':'subtitle'}];cases.append((board,d,receipts))
 d=copy.deepcopy(details);d['duration']+=1;cases.append((board,d,receipts))
 for b,d,r in cases:
  try:final_receipt(proof,b,final,d,contract,r)
  except ValueError:pass
  else:raise AssertionError('invalid final handoff accepted')
print('PASS: complete final handoff; missing scene, proof/narration/timing/scene mismatch, missing subtitles/audio, wrong duration rejected')
