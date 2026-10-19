"""Uploaded notes: real file extraction, useful failures, no paid model calls."""
import importlib.util,sys,tempfile,os
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from worker_test_support import WorkerClient
spec=importlib.util.spec_from_file_location('server_notes_test',ROOT/'web/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);private=root/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32));projects=root/'projects'
 with patch.object(server,'PRIVATE',private),patch.object(server,'STUDIO_PROJECTS',projects),patch.object(server,'jobs',{}),patch.object(server.executor,'submit') as submit,patch.object(server.editing_service,'jobs',{}):
  c=WorkerClient(server);form={'prompt':'请依据上传笔记做复盘，先知识地图再回忆小测','style':'studio_editorial','template_id':'notes','duration':'180'}
  for filename,content in [('empty.txt',b''),('short.txt','只有四个字'.encode()),('broken.txt',b'\xff\xfe\x00'),('scanned.pdf',b'not a PDF'),('audio.mp3',b'no notes')]:
   r=c.post('/api/jobs',data=form,files=[('files',(filename,content,'application/octet-stream'))]);assert r.status_code==400,(filename,r.status_code,r.text)
  assert submit.call_count==0
  content=(ROOT/'templates/examples/review-notes.md').read_bytes()
  r=c.post('/api/jobs',data=form,files=[('files',('lesson.md',content,'text/markdown'))]);assert r.status_code==202,r.text
  assert submit.call_count==1
  args=submit.call_args.args;config=args[4];assert config['task']['template_id']=='notes' and config['video']['target_duration']==180
  assert not config['teaching_research']['enabled']
server.executor.shutdown(wait=False)
print('PASS: notes require usable text; empty/short/malformed/binary files fail clearly; valid notes snapshot template, duration, and avoid unrelated search.')
