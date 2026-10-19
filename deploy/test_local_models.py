"""Submit an original sketch exam lesson using the owner's local model configuration.

No secrets are printed or stored in the local test report. The Go API freezes the
per-task configuration encrypted; existing personal and platform settings stay intact.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from configuration import load_config, sanitize_error
from dotenv import load_dotenv
import httpx

PROMPT = '''制作一段约90秒的原创考公行测数量关系教学视频，只用手绘课堂风格。
题目：一块草地匀速长草，每头牛每天吃草量相同。24头牛6天吃完，21头牛8天吃完，18头牛几天吃完？选项 A.10天 B.12天 C.14天 D.16天。
事实核验：24×6=144，21×8=168；每天增长(168−144)/(8−6)=12份；原有草量(24−12)×6=72份；18头牛每天净消耗18−12=6份；72÷6=12天，选B。代回21头牛：72÷(21−12)=8天。
教学重点：解释为什么不能直接用牛数与天数的反比例。以草地、简笔画牛、增长和净消耗色条逐步呈现，不要满屏公式。
美术：暖白纸张、轻微手绘线条，深蓝主色、绿色增长、橙色净消耗，中文标题清晰，充分留白。分镜由题目、求增长、解释净消耗、求原草量、计算答案、代回检验组成。
中文配音与画面同步，每个结论停留足够阅读时间；避免文字重叠、公式越界、字幕遮挡关键内容。'''
FIELDS = ('base_url', 'model', 'api_key', 'protocol', 'max_tokens', 'fallback_models', 'stream', 'extra_body')


def task_config(local):
    config = {'use_platform': False, 'vision_inherit': False,
              'tts': {'provider': 'edge', 'voice': 'zh-CN-YunxiNeural'}}
    for role, title in (('text', '内容生成'), ('vision', '视觉审核')):
        channel = {name: local[role][name] for name in FIELDS if name in local[role]}
        for name in ('base_url', 'model', 'api_key'):
            if not isinstance(channel.get(name), str) or not channel[name].strip() or '${' in channel[name]:
                label = {'base_url': '服务地址', 'model': '模型名称', 'api_key': '密钥'}[name]
                raise ValueError(f'{title}{label}未配置；请提供实际本地配置或密钥文件。')
        channel.setdefault('fallback_models', [])
        channel.setdefault('protocol', 'chat_completions')
        config[role] = channel
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.local.json')
    parser.add_argument('--env-file', type=Path, help='Explicit authorized key file, loaded without printing values')
    parser.add_argument('--base-url', default='http://127.0.0.1:7860')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--submit', action='store_true')
    action.add_argument('--job', help='Poll an existing job once; never resubmit it')
    args = parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            raise ValueError('指定的密钥文件不存在。')
        load_dotenv(args.env_file, override=True)
    local = load_config(args.config)
    config = None if args.job else task_config(local)
    if config:
        for role in ('text', 'vision'):
            print(role, ' -> '.join([config[role]['model'], *config[role]['fallback_models']]))
        print('配音：免费在线配音；画面：手绘课堂；生成与审核均使用本地模型配置。')
    if not args.submit and not args.job:
        print('PASS: local model configuration is complete. Use --submit to start the real test.')
        return
    if args.job and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.job):
        raise ValueError('任务编号格式不正确。')
    credentials = dict(line.split('=', 1) for line in (ROOT / 'private/admin-access.txt').read_text().splitlines())
    with httpx.Client(base_url=args.base_url, timeout=45, trust_env=False,
                      headers={'X-Frame-Request': '1'}) as client:
        def checked(response):
            if response.is_error:
                raise ValueError(sanitize_error(response.text, local)[:800])
            return response.json()
        checked(client.post('/api/auth/login', json={'username': credentials['USERNAME'], 'password': credentials['PASSWORD']}))
        try:
            if args.submit:
                result = checked(client.post('/api/jobs', json={'prompt': PROMPT, 'style': 'studio_sketch',
                    'duration': 90, 'orientation': 'landscape', 'auto_approve': True,
                    'reference_urls': [], 'source_ids': [], 'config': config}))
                report = {'job_id': result['id'], 'submitted_at': datetime.now(timezone.utc).isoformat(),
                    'source_config': str(args.config), 'style': 'studio_sketch',
                    'models': {role: [config[role]['model'], *config[role]['fallback_models']] for role in ('text', 'vision')}}
                path = ROOT / '.tmp/live-exam-test.json';path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
                print('Submitted job:', result['id'])
                print('Poll with: .venv/bin/python deploy/test_local_models.py --job', result['id'])
            else:
                result = checked(client.get('/api/jobs/' + args.job))
                summary = {name: result.get(name) for name in ('id', 'status', 'stage', 'message', 'video', 'review')}
                print(sanitize_error(json.dumps(summary, ensure_ascii=False), local))
                if result.get('status') == 'complete':
                    usage = checked(client.get('/api/jobs/' + args.job + '/usage'))
                    path = ROOT / '.tmp' / ('live-exam-usage-' + args.job + '.json')
                    path.write_text(json.dumps(usage, ensure_ascii=False, indent=2))
                    print('Usage report:', path)
        finally:
            client.post('/api/auth/logout')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, httpx.HTTPError) as error:
        # Transport errors do not include request headers; configuration failures are explicit.
        print('TEST NOT STARTED / INCOMPLETE:', str(error), file=sys.stderr)
        sys.exit(2)
