"""Reproducible human art-direction pass for the real generated exam lesson.

Preserves planning, narration and archived runtime. Never touches a running job.
Render first, inspect frames, then review and publish; every changed video gets
a new revision and a fresh model review. Original artifacts remain available.
"""
import argparse
import json
import re
import shutil
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from configuration import load_config
from execution import project_lock
from lesson_prompts import review_prompt
from media import ffmpeg_binary, probe, run_command, sample_beat_frames
from pipeline import VideoPipeline, save_json, validate_code
from video_project import restore_credentials


def text(name, label, x, y, size=30, color='foreground'):
    return f'{name} = self.scene_text({label!r}, {size}, self.style_color({color!r})).move_to([{x}, {y}, 0])\n'


def box(name, x, y, w, h, color='primary', fill=False):
    filling = f', fill=self.style_color({color!r})' if fill else ''
    return f'{name} = self.sketch_shape("rectangle", width={w}, height={h}, center=[{x},{y},0], color=self.style_color({color!r}){filling})\n'


def show(*names, duration=.65):
    return 'self.play(' + ', '.join(f'FadeIn({n})' for n in names) + f', run_time={duration})\n'


def snippets():
    # Content lives between y=-2.1 and y=2.1; title and captions have their own rails.
    a = text('intro', '同一块草地 · 匀速生长 · 每头牛食量相同', 0, 1.95, 28, 'muted')
    a += box('card1', -3, .8, 5.1, 1.35) + box('card2', 3, .8, 5.1, 1.35)
    a += text('n1', '24 头牛 → 6 天', -3, .8, 35, 'primary') + text('n2', '21 头牛 → 8 天', 3, .8, 35, 'primary')
    a += show('intro', 'card1', 'card2', 'n1', 'n2')
    a += 'grass = self.sketch_shape("ellipse", width=2.4, height=.6, center=[-3,-1,0], color=self.style_color("secondary"))\n'
    a += 'cow = self.sketch_shape("ellipse", width=1.1, height=.5, center=[-3,-.65,0])\nhead = self.sketch_shape("ellipse", width=.35, height=.32, center=[-2.4,-.58,0])\n'
    a += 'legs = VGroup(*[self.sketch_line([x,-.85,0],[x,-1.15,0]) for x in [-3.35,-2.7]])\n'
    a += text('q', '18 头牛，需要几天？', 2.1, -.7, 35, 'emphasis') + show('grass', 'cow', 'head', 'legs', 'q')
    a += text('options', 'A. 10 天     B. 12 天     C. 14 天     D. 16 天', 0, -1.95, 29) + show('options')

    b = text('one', '原有草量', 0, 1.85, 32, 'primary') + box('stock', 0, .35, 3.8, 1.6, 'primary')
    b += text('stock_label', '草地里的草', 0, .35, 30) + show('one', 'stock', 'stock_label')
    b += text('growth', '草在长', -4.25, 1.3, 32, 'secondary') + text('eaten', '牛在吃', 4.25, 1.3, 32, 'emphasis')
    b += 'up = self.sketch_line([-5.4,.35,0],[-2.15,.35,0],color=self.style_color("secondary"),arrow=True)\n'
    b += 'down = self.sketch_line([2.15,.35,0],[5.4,.35,0],color=self.style_color("emphasis"),arrow=True)\n'
    b += show('growth', 'eaten') + 'self.play(Create(up), Create(down), run_time=1)\n'
    b += text('feature', '原草量 + 持续增长 + 持续消耗', 0, -1, 31) + text('rule', '两组“牛数—天数”条件，求同一份原草量', 0, -1.95, 27, 'muted') + show('feature', 'rule')

    c = text('unit', '约定：每头牛每天吃 1 份草', 0, 1.95, 28, 'muted')
    c += text('lab1', '24 × 6', -4.8, .9, 31) + text('lab2', '21 × 8', -4.8, -.25, 31)
    # Same scale: 144 -> 6 units, 168 -> 7 units; extra 24 -> 1 unit.
    c += box('bar1', 0, .9, 6, .5, 'primary', True) + box('bar2', 0, -.25, 6, .5, 'primary', True)
    c += box('extra', 3.5, -.25, 1, .5, 'secondary', True)
    c += text('v1', '144 份', 5.05, .9, 30, 'primary') + text('v2', '168 份', 5.05, -.25, 30, 'primary')
    c += show('unit', 'lab1', 'lab2') + 'self.play(Create(bar1), Create(bar2), Create(extra), run_time=1.2)\n' + show('v1', 'v2')
    c += text('delta', '多出的 24 份，来自多长的 2 天', 0, -1.2, 31, 'secondary')
    c += text('trap', '总吃草量不相等，不能直接用反比例', 0, -2.05, 28, 'emphasis') + show('delta', 'trap')

    d = text('diff', '168 − 144 = 24 份', -2.7, 1.85, 33, 'secondary') + text('days', '8 − 6 = 2 天', 3.25, 1.85, 33, 'primary')
    d += box('day7', -2.6, .5, 4.5, .65, 'secondary', True) + box('day8', 2.6, .5, 4.5, .65, 'secondary', True)
    d += text('d7', '第 7 天新长的草', -2.6, -.25, 27) + text('d8', '第 8 天新长的草', 2.6, -.25, 27)
    d += show('diff', 'days') + 'self.play(Create(day7), Create(day8), run_time=1.2)\n' + show('d7', 'd8')
    d += text('result', '每天长：24 ÷ 2 = 12 份', 0, -1.45, 40, 'secondary') + show('result')

    e = text('formula', '净消耗 = 牛吃掉的 − 草长回的', 0, 1.85, 34)
    e += text('eat', '每天吃 24', -4.6, .7, 29, 'emphasis') + box('eatbar', .6, .7, 7.2, .5, 'emphasis', True)
    e += text('grow', '每天长 12', -4.6, -.25, 29, 'secondary') + box('growbar', -1.2, -.25, 3.6, .5, 'secondary', True)
    e += show('formula', 'eat', 'grow') + 'self.play(Create(eatbar), Create(growbar), run_time=1.1)\n'
    e += box('netbar', 2.4, -.25, 3.6, .5, 'emphasis', True) + 'self.play(Create(netbar), run_time=.7)\n'
    e += text('net', '草地每天真正减少：24 − 12 = 12 份', 0, -1.5, 34, 'emphasis') + show('net')

    f = text('method', '原草量 = 每天净消耗 × 天数', 0, 1.85, 34, 'primary')
    f += box('left', -3.1, .5, 5.25, 1.6) + box('right', 3.1, .5, 5.25, 1.6, 'secondary')
    f += text('lt', '用 24 头牛计算', -3.1, .95, 27, 'muted') + text('rt', '用 21 头牛核验', 3.1, .95, 27, 'muted')
    f += text('lc', '(24 − 12) × 6', -3.1, .1, 32, 'primary') + text('rc', '(21 − 12) × 8', 3.1, .1, 32, 'secondary')
    f += show('method', 'left', 'lt', 'lc') + show('right', 'rt', 'rc')
    f += 'arrows = VGroup(self.sketch_line([-3,-.55,0],[-1.5,-1.15,0],arrow=True),self.sketch_line([3,-.55,0],[1.5,-1.15,0],arrow=True))\n'
    f += 'self.play(Create(arrows), run_time=.7)\n' + text('total', '同得 72 份', 0, -1.65, 43, 'primary') + show('total')

    g = text('net', '18 头牛：每天净消耗 18 − 12 = 6 份', 0, 1.85, 33)
    g += text('explain', '原草量 72 份，分成 12 组；每组 6 份，恰好够 1 天', 0, 1, 26, 'muted') + show('net', 'explain')
    g += 'blocks = VGroup(*[self.sketch_shape("rectangle", width=.7,height=.6,center=[-4.95+i*.9,0,0],color=self.style_color("secondary"),fill=self.style_color("secondary")) for i in range(12)])\n'
    g += 'self.play(LaggedStart(*[FadeIn(block) for block in blocks],lag_ratio=.08),run_time=1.2)\nself.wait(1)\n'
    g += 'self.play(LaggedStart(*[FadeOut(block) for block in blocks],lag_ratio=.12),run_time=2.4)\n'
    g += text('answer', '72 ÷ 6 = 12 天', -.8, -1.25, 44, 'primary') + box('choice', 4, -1.25, 1.55, 1, 'emphasis') + text('b', '选 B', 4, -1.25, 33, 'emphasis') + show('answer', 'choice', 'b')

    h = text('check', '换回题干里的 21 头牛', 0, 1.85, 33, 'primary') + text('daily', '每天净消耗：21 − 12 = 9 份', 0, .95, 33)
    h += 'blocks = VGroup(*[self.sketch_shape("rectangle",width=.85,height=.6,center=[-3.85+i*1.1,0,0],color=self.style_color("secondary"),fill=self.style_color("secondary")) for i in range(8)])\n'
    h += show('check', 'daily') + 'self.play(LaggedStart(*[FadeIn(block) for block in blocks],lag_ratio=.1),run_time=1)\n'
    h += text('result', '72 ÷ 9 = 8 天', 0, -1.1, 42, 'secondary') + text('agree', '每组 9 份，8 组吃完；与题干一致', 0, -2.05, 28, 'muted') + show('result', 'agree')

    i = ''
    for idx, (x, title, equation, color) in enumerate([(-4,'① 求草长速度','24 ÷ 2 = 12','secondary'),(0,'② 求净消耗','18 − 12 = 6','emphasis'),(4,'③ 求所需天数','72 ÷ 6 = 12','primary')]):
        i += box('card'+str(idx), x, .9, 3.55, 1.8, color)
        if idx == 0:
            i += text('title0', title, x, 1.45, 26, color) + text('eq0', '草量差 ÷ 天数差', x, .9, 24)
            i += text('units', '24 ÷ 2 = 12 份/天', x, .35, 22, color) + show('card0','title0','eq0','units')
        else:
            i += text('title'+str(idx), title, x, 1.35, 28, color) + text('eq'+str(idx), equation, x, .45, 27)
            i += show('card'+str(idx), 'title'+str(idx), 'eq'+str(idx))
    i += text('remember', '先减去草长速度，再用原草量去除', 0, -.8, 36, 'primary') + text('wrong', '不能用 72 ÷ 18：漏掉了每天新长的草', 0, -1.95, 29, 'emphasis') + show('remember', 'wrong')
    return {f'section_{n+1}': {'beats': [{'code': c} for c in group]} for n, group in enumerate([(a,b,c),(d,e,f),(g,h,i)])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', default='938eef858abc')
    parser.add_argument('--section', choices=['section_1','section_2','section_3'], help='Render only one further refinement')
    parser.add_argument('stage', choices=['validate', 'render', 'review', 'publish'])
    args = parser.parse_args()
    project = ROOT / 'video_projects' / ('studio-' + args.job)
    output = project / 'output'
    metadata = json.loads((project / 'studio_job.json').read_text())
    manifest = json.loads((output / 'manifest.json').read_text())
    codes = snippets()
    for value in codes.values():
        validate_code(value, 3, video=manifest['config']['video'])
    if args.stage == 'validate':
        print('PASS: 9 polished beats satisfy code and palette contracts')
        return
    if metadata['status'] in ('running', 'queued', 'revising'):
        raise RuntimeError('The existing worker job is still active; leave it undisturbed.')
    with project_lock(project):
        config = restore_credentials(manifest['config'], load_config(ROOT / 'config.local.json'))
        pipe = VideoPipeline(manifest['topic'], config, output, project=project, resume=True)
        storyboard = json.loads((output / 'storyboard_assets.json').read_text())
        polish = output / 'human_polish'
        polish.mkdir(exist_ok=True)
        pointer = polish / 'rendered.json'
        if args.stage == 'render':
            if pointer.exists() and not args.section:
                raise RuntimeError('Polish already rendered; inspect or review existing output.')
            for name in ['manifest.json','storyboard_assets.json','reviewed.json','review_status.json']:
                if (output/name).exists() and not (polish/name).exists():
                    shutil.copy2(output/name, polish/name)
            rendered = json.loads(pointer.read_text()) if pointer.exists() else {}
            if (polish/'storyboard.json').exists():
                storyboard = json.loads((polish/'storyboard.json').read_text())
            for section in storyboard['sections']:
                sid = section['id']
                if args.section and sid != args.section:
                    continue
                if not (polish / (sid+'_original_code.json')).exists():
                    shutil.copy2(output / (sid+'_code.json'), polish / (sid+'_original_code.json'))
                revision = max([int(f.name.split('_')[-1]) for f in (output/sid).glob('revision_*')]+[0])+1
                for beat in section['beats']:
                    for cue in beat.get('subtitles', []):
                        cue['text'] = cue['text'].rstrip('。')
                        if sid == 'section_3':
                            cue['text'] = cue['text'].replace('72除以21减12等于8天', '72÷(21−12)=8天')
                        lines = textwrap.wrap(cue['text'], width=32)
                        if any(a[-1:].isdigit() and b[:1].isdigit() for a,b in zip(lines, lines[1:])):
                            # The archived renderer wraps at whitespace; keep spoken numbers intact.
                            cue['text'] = cue['text'].replace('所以', ' 所以') if '所以' in cue['text'] else re.sub(r'(\d+)', r' \1 ', cue['text'])
                # Diagrams now use exact continuous ratios or explicit units.
                if sid == 'section_1':
                    section['beats'][2]['visual'] = '同尺度手绘条形图144:168，后者多出24份；标签在色条之外。'
                if sid == 'section_2':
                    section['beats'][2]['visual'] = '两条独立计算路径，用箭头指向唯一的72份原草量结果。'
                save_json(polish/(sid+'_code.json'), codes[sid])
                print('Rendering', sid, 'revision', revision, flush=True)
                video = pipe.render(section, codes[sid], revision)
                rendered[sid] = {'video': str(video), 'revision': revision}
                save_json(polish/'progress.json', rendered)
            save_json(polish/'storyboard.json', storyboard)
            save_json(pointer, rendered)
        elif args.stage == 'review':
            rendered = json.loads(pointer.read_text())
            storyboard = json.loads((polish/'storyboard.json').read_text())
            for section in storyboard['sections']:
                sid = section['id']; artifact = rendered[sid]
                review_file = polish/(sid+'_review.json')
                if review_file.exists():
                    previous = json.loads(review_file.read_text())
                    if previous.get('reviewed_revision') == artifact['revision'] and not previous['has_issues']:
                        continue
                frames = sample_beat_frames(Path(artifact['video']), polish/sid, section['beats'], 12)
                feedback = pipe.vision.json(pipe.prompt('review', review_prompt(section, pipe.templates)), pipe.validate_feedback, images=frames)
                feedback['reviewed_revision'] = artifact['revision']
                save_json(review_file, feedback)
                print(sid, json.dumps(feedback, ensure_ascii=False), flush=True)
        else:
            rendered = json.loads(pointer.read_text())
            for sid, artifact in rendered.items():
                feedback = json.loads((polish/(sid+'_review.json')).read_text())
                if feedback['has_issues'] or feedback['reviewed_revision'] != artifact['revision']:
                    raise RuntimeError('Changed video must pass a fresh visual review: '+sid)
            for sid in rendered:
                save_json(output/(sid+'_code.json'), json.loads((polish/(sid+'_code.json')).read_text()))
                save_json(output/(sid+'_review_99.json'), json.loads((polish/(sid+'_review.json')).read_text()))
            save_json(output/'storyboard_assets.json', json.loads((polish/'storyboard.json').read_text()))
            save_json(output/'reviewed.json', rendered)
            final = pipe.run()
            poster = output/'poster.jpg'
            run_command([ffmpeg_binary(),'-y','-ss','43','-i',str(final),'-frames:v','1','-vf','scale=960:-2',str(poster)])
            metadata.update(status='complete', stage='compose', stage_status='complete',
                message='真实模型生成，已完成人工画面优化及重新视觉审核', updated_at=time.time(),
                video=f'/api/jobs/{args.job}/video', subtitles=f'/api/jobs/{args.job}/subtitles',
                poster=f'/api/jobs/{args.job}/poster', review=pipe.manifest['visual_review'])
            save_json(project/'studio_job.json', metadata)
            save_json(polish/'acceptance.json', {'job':args.job,'human_directed':True,'original_model_generated':True,
                'revisions':rendered,'review':pipe.manifest['visual_review'],'media':probe(final)})
            print('Published polished video:', final)


if __name__ == '__main__':
    main()
