"""Check the completed film, not just its intermediate animation. No API calls."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from logic_contract import solve
from logic_acceptance import final_receipt
from media import probe,sample_frames
from video_project import input_fingerprint,write_json
p=argparse.ArgumentParser();p.add_argument('project',type=Path);a=p.parse_args();project=a.project.resolve();out=project/'output';manifest=json.loads((out/'manifest.json').read_text())
assert manifest['status']=='complete' and manifest.get('visual_review',{}).get('passed') is True,'Film not approved'
assert manifest['inputs_fingerprint']==input_fingerprint(project),'Frozen project inputs changed'
proof=json.loads((out/'logic_proof.json').read_text());materials=json.loads((out/'materials.json').read_text());recomputed=solve(proof['contract'],manifest['topic']+'\n'+materials.get('context',''));assert recomputed==proof
assert json.loads((out/'logic_semantic_audit.json').read_text())['proof_hash']==proof['proof_hash']
board=json.loads((out/'timing.json').read_text());rendered=json.loads((out/'reviewed.json').read_text());receipts=[]
for s in board['sections']:
 r=json.loads(Path(rendered[s['id']]['video']).with_suffix('.receipt.json').read_text());receipts.append(r)
 source=project/'code/runtime/logic_renderer.py'
 if not source.exists():source=out/'acceptance/runtime/logic_renderer.py'
 assert hashlib.sha256(source.read_bytes()).hexdigest()==r['renderer_sha256'],'Renderer source not archived'
final=out/'final.mp4';details=probe(final)
import logic_contract
record=final_receipt(proof,board,final,details,logic_contract,receipts)
subprocess.run(['ffmpeg','-v','error','-nostdin','-threads','1','-i',str(final),'-f','null','-'],check=True,timeout=240)
# Three times in each scene catch both early reveal and stale highlight states.
cursor=0;positions=[]
for s in board['sections']:
 for b in s['beats']:
  positions.extend(cursor+b['duration']*x for x in (.2,.55,.85));cursor+=b['duration']
frames=sample_frames(final,out/'acceptance/final_frames',positions=positions)
canvas=Image.new('RGB',(1920,1080*3),'white')
for i,path in enumerate(frames):
 with Image.open(path) as im:canvas.paste(im.resize((640,360)),((i%3)*640,(i//3)*540))
canvas.save(out/'acceptance/final-contact.jpg')
record['checks'].append('entire final film decoded');record['final_frame_positions']=positions
write_json(out/'logic_final_acceptance.json',record)
print(json.dumps({'project':project.name,'duration':details['duration'],'proof':proof['proof_hash'],'final_sha256':record['final_sha256'],'frames':len(frames),'streams':details['streams']},ensure_ascii=False))
