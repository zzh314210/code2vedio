"""Serial real sample production; failures retained, never auto-published."""
from pathlib import Path
import argparse,subprocess,json,time,os
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--revision',default='v4');p.add_argument('--templates',nargs='+',default=['product','math_visual','explainer','history_map','word_story','documentary','notes']);p.add_argument('--after-pid',type=int);p.add_argument('--resume',action='store_true');a=p.parse_args()
if a.after_pid:
 while True:
  try:os.kill(a.after_pid,0)
  except ProcessLookupError:break
  time.sleep(15)
out=ROOT/('.tmp/showcase-batch-'+a.revision);out.mkdir(parents=True,exist_ok=True)
for template in a.templates:
 record={'template':template,'status':'running','started_at':time.time()};(out/(template+'.json')).write_text(json.dumps(record))
 with (out/(template+'.log')).open('w') as log:
  try:
   result=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'deploy/render_showcase_local.py'),template,'--revision',a.revision]+(['--resume'] if a.resume else []),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=4800)
   record.update(status='generated' if result.returncode==0 else 'needs_fix',exit_code=result.returncode,ended_at=time.time())
  except subprocess.TimeoutExpired:record.update(status='timed_out',ended_at=time.time())
 (out/(template+'.json')).write_text(json.dumps(record));print(json.dumps(record),flush=True)
