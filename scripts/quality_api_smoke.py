"""Delivery fails closed, quality reports stay private, optional subtitles work."""
import importlib.util,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from worker_test_support import WorkerClient
spec=importlib.util.spec_from_file_location('quality_api_test',ROOT/'web/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as td:
 root=Path(td);private=root/'private';private.mkdir();(private/'worker.key').write_bytes(os.urandom(32))
 p=root/'project';out=p/'output';(out/'quality').mkdir(parents=True)
 manifest={'config':{'quality':{'enabled':True},'video':{'subtitle_mode':'burn'}},'status':'complete'}
 (out/'manifest.json').write_text(json.dumps(manifest));(out/'final.mp4').write_bytes(b'not-accepted')
 (out/'quality/contract.json').write_text(json.dumps({'checks':[{'id':'known','requirement':'图形必须清楚'}]}));(out/'subtitles.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\n完整字幕\n')
 record={'id':'123456abcdef','owner_id':'a'*32,'status':'complete','style':'studio_sketch','project':str(p)}
 with patch.object(server,'PRIVATE',private),patch.object(server,'STUDIO_PROJECTS',root/'jobs'),patch.object(server,'jobs',{record['id']:record}):
  client=WorkerClient(server);other=WorkerClient(server,user='b'*32);url='/api/jobs/'+record['id']
  assert client.get(url+'/video').status_code==409,'unaccepted film downloadable'
  report=client.get(url+'/report');assert report.status_code==200 and report.json()['quality']['contract']['checks'][0]['id']=='known'
  for route in ('/report','/video','/subtitles'):assert other.get(url+route).status_code==404
  # Historical releases remain available through their original gate.
  manifest['config']['quality']['enabled']=False;(out/'manifest.json').write_text(json.dumps(manifest))
  assert client.get(url+'/video').status_code==200
  assert client.get(url+'/subtitles').status_code==200
  manifest['config']['video']['subtitle_mode']='off';(out/'manifest.json').write_text(json.dumps(manifest))
  assert client.get(url+'/subtitles').status_code==404
server.executor.shutdown(wait=True);server.revision_service.advice_pool.shutdown(wait=False)
print('PASS: missing/invalid acceptance blocks download, legacy deliveries preserved, complete reports isolated per owner, disabled captions not exposed')
