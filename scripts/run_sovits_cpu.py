"""Start the pinned upstream service on CPU, with a pure-Python Jieba compatibility alias."""
import argparse
import os
import runpy
import sys
from pathlib import Path

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('repo');parser.add_argument('--port',type=int,default=9880);args=parser.parse_args()
    root=Path(args.repo).resolve();os.chdir(root);sys.path[:0]=[str(root),str(root/'GPT_SoVITS')]
    os.environ.setdefault('OMP_NUM_THREADS','8')
    import torch
    torch.set_num_threads(8)
    # jieba_fast's C extension does not build on CPython 3.12/Windows. Jieba
    # exposes the same tokenizer API; this does not change model weights.
    import jieba
    import jieba.posseg
    import jieba.finalseg
    sys.modules['jieba_fast']=jieba
    sys.modules['jieba_fast.posseg']=jieba.posseg
    sys.modules['jieba_fast.finalseg']=jieba.finalseg
    sys.argv=['api_v2.py','-a','127.0.0.1','-p',str(args.port),'-c',str(root/'cpu-infer.yaml')]
    runpy.run_path(str(root/'api_v2.py'),run_name='__main__')
