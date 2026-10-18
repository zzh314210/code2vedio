import concurrent.futures
import hashlib
from pathlib import Path
from urllib.parse import quote
import argparse
import requests

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args();root=Path(args.directory);root.mkdir(parents=True,exist_ok=True)
    host='https://www.modelscope.cn';repo='pengzhendong/faster-whisper-small'
    response=requests.get(f'{host}/api/v1/models/{repo}/repo/files?Recursive=true',timeout=30);response.raise_for_status()
    files=[item for item in response.json()['Data']['Files'] if item['Path'] in ('config.json','model.bin','tokenizer.json','vocabulary.txt')]
    def download(item):
        target=root/item['Path'];expected=item.get('Sha256')
        if target.is_file() and target.stat().st_size==item['Size']:return
        temporary=target.with_suffix(target.suffix+'.download');digest=hashlib.sha256();size=0
        with requests.get(f"{host}/models/{repo}/resolve/master/"+quote(item['Path']),stream=True,timeout=(20,60)) as r:
            r.raise_for_status()
            with temporary.open('wb') as out:
                for chunk in r.iter_content(1024*1024):digest.update(chunk);size+=len(chunk);out.write(chunk)
        if size!=item['Size'] or (expected and digest.hexdigest()!=expected):raise ValueError('ASR model size/hash mismatch')
        temporary.replace(target);print('Downloaded '+item['Path'],flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,files))
    print('CPU ASR model ready: '+str(root),flush=True)
