"""Opt-in real model and FFmpeg acceptance using existing private test fixtures.

Consumes the locally configured model API; artifacts remain outside tracked files.
Run under the deployment resource slice, with the production queue idle.
"""
import argparse, copy, json, os, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from configuration import load_config, sanitize_error
from editing import analyze, render, review_edit, validate_clips
from model_gateway import ModelGateway

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--fixtures', type=Path, default=ROOT / '.tmp/staging/projects')
parser.add_argument('--mode', action='append', choices=['product','highlights','gaming','documentary'])
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
config = load_config(ROOT / 'config.local.json', overrides={
    'text': {'model': 'kimi-k3', 'fallback_models': ['deepseek-v4.1-flash-1017']},
    'vision': {'model': 'deepseek-v4.1-flash', 'fallback_models': ['qwen3.8-flash']},
})
for role in ['text', 'vision']:
    config[role]['usage_file'] = str(args.out / 'usage.jsonl')
cases = [
    ('product', 'edit-e5e0045ed1c3', 60, '这是原创产品演示素材。围绕视频工作台这一产品，保留具体操作、功能价值和原片中的限制，剪成一分钟。不要添加原片没有的价格。'),
    ('highlights', 'edit-e5e0045ed1c3', 30, '剪出视频工作台操作的精华，只讲从输入想法到预览成片的核心过程。去掉重复，保留完整解释与结论。'),
    ('gaming', 'edit-382ef1395832', 30, '保留赛车连续过弯的精彩操作，保持原始事件顺序、入弯铺垫和出弯结果，删除无意义的直线行驶，不编造胜负。'),
    ('documentary', 'edit-e5e0045ed1c3', 45, '以纪实方式记录一次视频制作：从输入材料、选择样式，到预览和完成的过程。按实际操作顺序组织，保留原声和必要说明，不使用聚焦动效。'),
]
results = []
for mode, fixture, duration, prompt in cases:
    if args.mode and mode not in args.mode:continue
    directory = args.out / mode
    directory.mkdir(exist_ok=True)
    start = time.monotonic()
    try:
        original = args.fixtures / fixture
        record = json.loads((original / 'editing_job.json').read_text())
        record.update(mode=mode, prompt=prompt, target_duration=duration, captions=True)
        for source in record['sources']:
            target = directory / source['file']
            if not target.exists():
                os.link(original / source['file'], target)
            # Reuse proven local ASR, but regenerate all model observations/plans.
            local = directory / source['id']
            local.mkdir(exist_ok=True)
            shutil.copy2(original / source['id'] / 'analysis.json', local / 'analysis.json')
        events = []
        def event(stage, message):
            events.append({'stage': stage, 'message': message})
            print(mode, stage, message, flush=True)
        sources, plan = analyze(directory, copy.deepcopy(record), config, event)
        record['sources'] = sources
        validate_clips(plan, sources, mode=mode, speech_safe=True)
        review = review_edit(directory, sources, plan, ModelGateway(config['text']), mode)
        assert review['passed'], review['issues']
        (directory / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        actual = render(directory, record, plan, event)
        result = {'mode': mode, 'passed': True, 'actual': actual, 'clips': len(plan['clips']), 'quality': review['notes'], 'events': events}
    except Exception as error:
        if getattr(error,'candidate',None):
            (directory/'rejected-plan.json').write_text(json.dumps(error.candidate,ensure_ascii=False,indent=2))
        result = {'mode': mode, 'passed': False, 'error': sanitize_error(str(error))}
    result['seconds'] = round(time.monotonic() - start, 2)
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    results.append(result)
    (args.out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(mode, 'PASS' if result['passed'] else 'FAIL: ' + result['error'], flush=True)
assert all(result['passed'] for result in results), 'Inspect results.json for failed templates'
