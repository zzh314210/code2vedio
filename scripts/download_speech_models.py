"""Download the minimal GPT-SoVITS CPU inference models from the official ModelScope mirror."""
import argparse
import concurrent.futures
import hashlib
import json
import zipfile
from pathlib import Path
from urllib.parse import quote
import requests

BASE="https://www.modelscope.cn/models/XXXXRT/GPT-SoVITS-Pretrained/resolve/master/"
WANTED=["pretrained_models/fast_langdetect/lid.176.bin","pretrained_models/fast_langdetect/lid.176.ftz","pretrained_models/chinese-hubert-base/config.json","pretrained_models/chinese-hubert-base/preprocessor_config.json","pretrained_models/chinese-hubert-base/pytorch_model.bin","pretrained_models/chinese-roberta-wwm-ext-large/config.json","pretrained_models/chinese-roberta-wwm-ext-large/tokenizer.json","pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin","pretrained_models/s1v3.ckpt","pretrained_models/v2Pro/s2Gv2ProPlus.pth","pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt","G2PWModel.zip"]

def fetch(item,root,index):
    meta=index[item]
    target=root/("GPT_SoVITS/"+item if item.startswith("pretrained_models/") else item)
    target.parent.mkdir(parents=True,exist_ok=True)
    expected=meta.get("Sha256") or meta.get("SHA256")
    if target.is_file() and target.stat().st_size==meta["Size"]:
        if not expected or hashlib.sha256(target.read_bytes()).hexdigest()==expected:return str(target)
    temporary=target.with_suffix(target.suffix+".download")
    digest=hashlib.sha256();size=0
    with requests.get(BASE+quote(item,safe='/'),stream=True,timeout=(20,60)) as response:
        response.raise_for_status()
        with temporary.open('wb') as output:
            for chunk in response.iter_content(1024*1024):
                size+=len(chunk);digest.update(chunk);output.write(chunk)
    if size!=meta["Size"] or (expected and digest.hexdigest()!=expected):raise ValueError("Model checksum/size mismatch: "+item)
    temporary.replace(target)
    print("Downloaded "+item+f" ({size/1e6:.1f} MB)",flush=True)
    return str(target)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('repo');args=parser.parse_args();root=Path(args.repo).resolve()
    response=requests.get('https://www.modelscope.cn/api/v1/models/XXXXRT/GPT-SoVITS-Pretrained/repo/files?Recursive=true',timeout=30);response.raise_for_status()
    index={x['Path']:x for x in response.json()['Data']['Files']}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda item:fetch(item,root,index),WANTED))
    destination=(root/'GPT_SoVITS/text').resolve()
    with zipfile.ZipFile(root/'G2PWModel.zip') as archive:
        for member in archive.infolist():
            if not (destination/member.filename).resolve().is_relative_to(destination):raise ValueError('Unsafe archive entry')
        archive.extractall(destination)
    config={'custom':{'version':'v2ProPlus','device':'cpu','is_half':False,'bert_base_path':'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large','cnhuhbert_base_path':'GPT_SoVITS/pretrained_models/chinese-hubert-base','t2s_weights_path':'GPT_SoVITS/pretrained_models/s1v3.ckpt','vits_weights_path':'GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth'}}
    # JSON is also valid YAML; no extra parser dependency for this bootstrap script.
    (root/'cpu-infer.yaml').write_text(json.dumps(config,indent=2),encoding='utf8')
    print('CPU model set ready: '+str(root/'cpu-infer.yaml'))
