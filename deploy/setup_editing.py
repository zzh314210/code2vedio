"""Provision isolated free CPU editing tools; run explicitly on the deployment host."""
import hashlib,json,subprocess,urllib.request,venv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];environment=ROOT/'.venv-editing'
if not (environment/'bin/python').is_file():venv.create(environment,with_pip=True)
subprocess.run([str(environment/'bin/python'),'-m','pip','install','-r',str(ROOT/'requirements-editing.txt')],check=True)
manifest=json.loads((ROOT/'deploy/editing-model.json').read_text());target=ROOT/'private/models/whisper-small';target.mkdir(parents=True,exist_ok=True)
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
for name,expected in manifest['files'].items():
 if name not in ['config.json','model.bin','tokenizer.json','vocabulary.txt']:raise ValueError('Unexpected model asset')
 path=target/name
 if path.is_file() and digest(path)==expected['sha256']:continue
 temporary=path.with_suffix(path.suffix+'.download')
 url='https://huggingface.co/'+manifest['repository']+'/resolve/'+manifest['revision']+'/'+name
 with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as out:
  for chunk in iter(lambda:response.read(1024*1024),b''):out.write(chunk)
 if temporary.stat().st_size!=expected['bytes'] or digest(temporary)!=expected['sha256']:
  temporary.unlink();raise ValueError('Model asset integrity check failed: '+name)
 temporary.replace(path)
subprocess.run([str(environment/'bin/python'),'-c',"from faster_whisper import WhisperModel; WhisperModel("+repr(str(target))+",device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True); print('Local editing model ready')"],check=True)
print('Editing dependencies installed. No cloud speech API is required.')
