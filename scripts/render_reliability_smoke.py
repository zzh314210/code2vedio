"""Failure attribution, review evidence, and optional real bounded 1080p encode."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import execution
from pipeline import VideoPipeline, task_fingerprint, resume_vision_changed
from media import probe


def check_resource_resume():
    from copy import deepcopy
    config={'text':{'model':'fixed','max_tokens':24000},'vision':{'model':'review'},'execution':{'backend':'docker','image':'fixed-image','memory':'1g','cpus':1}}
    materials={'sources':[],'context':'same input'}
    existing={'config':deepcopy(config),'fingerprint':task_fingerprint('topic',config,materials)}
    updated=deepcopy(config);updated['execution']['memory']='2g'
    assert resume_vision_changed('topic',updated,materials,existing) is False
    updated['text']['max_tokens']=65536
    assert resume_vision_changed('topic',updated,materials,existing) is False
    updated['vision']['model']='new-review'
    assert resume_vision_changed('topic',updated,materials,existing) is True
    for path,value in [(('text','max_tokens'),12000),(('text','reasoning_effort'),'low'),(('text','model'),'changed'),(('execution','backend'),'trusted'),(('execution','image'),'another-image')]:
        candidate=deepcopy(config);candidate[path[0]][path[1]]=value
        try:resume_vision_changed('topic',candidate,materials,existing)
        except ValueError:pass
        else:raise AssertionError('unsafe cache reuse after '+str(path))
    print('PASS: resource-limit changes preserve paid caches; model, renderer and image changes cannot bypass cache validation')

check_resource_resume()

def check_failure_attribution():
    for code, detail, infrastructure in [(137, 'killed', True), (125, 'container unavailable', True),
                                         (1, 'MemoryError', True), (1, 'ValueError: bad animation', False)]:
        with patch.object(execution.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, '', detail)):
            try:
                execution._run(['docker'], ROOT, {}, 5, container=True)
            except RuntimeError as error:
                assert isinstance(error, execution.RenderInfrastructureError) == infrastructure
                assert str(code) in str(error)
            else:
                raise AssertionError('Nonzero renderer exit accepted')
    with tempfile.TemporaryDirectory() as temporary:
        pipe = VideoPipeline.__new__(VideoPipeline)
        pipe.output = Path(temporary)
        pipe.config = {'video': {'fix_attempts': 3}}
        pipe.text = Mock()
        pipe.render = Mock(side_effect=execution.RenderInfrastructureError('out of memory'))
        try:
            pipe.render_with_repairs({'id': 'test'}, {'beats': []}, 0)
        except execution.RenderInfrastructureError:
            pass
        else:
            raise AssertionError('Infrastructure error lost')
        pipe.render.assert_called_once()
        pipe.text.json.assert_not_called()
    with tempfile.TemporaryDirectory() as temporary:
        pipe=VideoPipeline.__new__(VideoPipeline);pipe.output=Path(temporary)
        pipe.config={'video':{'fix_attempts':2}};pipe.templates={};pipe.prompt=lambda stage,prompt:prompt
        pipe.validate_snippets=Mock();pipe.text=Mock()
        original={'beats':[{'code':'bad'}]};fixed={'beats':[{'code':'fixed'}]};section={'id':'s','beats':[{'narration':'a','duration':1}]}
        pipe.text.json.return_value=fixed
        pipe.render=Mock(side_effect=[RuntimeError('bad animation'),execution.RenderInfrastructureError('memory limit')])
        with patch('pipeline.code_prompt',return_value='repair'):
            try:pipe.render_with_repairs(section,original,0)
            except execution.RenderInfrastructureError:pass
            else:raise AssertionError('expected bounded resource failure')
        pipe.text.json.assert_called_once()
        pipe.text.json.reset_mock();pipe.render=Mock(return_value=Path(temporary)/'lesson.mp4')
        _,result,revision=pipe.render_with_repairs(section,original,0)
        assert result==fixed and revision==1
        pipe.text.json.assert_not_called()
        changed={'id':'s','beats':[{'narration':'different','duration':1}]}
        _,result,revision=pipe.render_with_repairs(changed,original,0)
        assert result==original and revision==0
    print('PASS: paid repair code survives infrastructure retries; changed storyboard cannot reuse it')
    print('PASS: infrastructure failures retain exit information and never trigger paid model repairs')


def check_review_evidence():
    pipe = VideoPipeline.__new__(VideoPipeline)
    pipe.templates = {}
    pipe.prompt = lambda stage, prompt: prompt
    section = {'id': 's', 'title': 'Test', 'beats': [{'narration': 'test', 'duration': 3, 'caption': 'test', 'visual': 'test'}]}
    clear = {'has_issues': False, 'suggested_improvements': []}
    issue = {'has_issues': True, 'suggested_improvements': ['A real overlap']}
    for opinions in [[clear], [issue, clear], [issue, issue]]:
        pipe.vision = SimpleNamespace(json=Mock(side_effect=opinions))
        result = pipe.assess_visual(section, ['actual-frame'], [1.5])
        assert result['has_issues'] == opinions[-1]['has_issues']
        assert pipe.vision.json.call_count == len(opinions)
        if len(opinions) > 1:
            assert result['initial_assessment'] == issue
            assert all(call.kwargs['images'] == ['actual-frame'] for call in pipe.vision.json.call_args_list)
    print('PASS: review confirmation preserves confirmed failures and original assessment with same frame evidence')


def check_real_encode():
    project = ROOT / '.tmp/bounded-render-check'
    output = project / 'output'
    output.mkdir(parents=True, exist_ok=True)
    scene = output / 'scene.py'
    scene.write_text('''from manim import *
import json
from pathlib import Path
class BoundedScene(Scene):
    def construct(self):
        assert config.max_inflight_encoders == 2
        assert config.encoder_queue_size == 2
        square = Square(fill_opacity=1, color=BLUE).shift(LEFT*4)
        self.add(square)
        self.play(square.animate.shift(RIGHT*8).rotate(PI), run_time=12, rate_func=linear)
        self.wait(18)
        root=Path(Path.cwd().anchor)/'sys'/'fs'/'cgroup'
        Path('memory.json').write_text(json.dumps({k:(root/k).read_text().strip() for k in ['memory.peak','memory.max']}))
''')
    log = execution.render_command([sys.executable, '-m', 'manim', '-qh', '--fps', '30', '--disable_caching',
                                    '--media_dir', str(output/'media'), str(scene), 'BoundedScene'],
                                   project, output, {'backend': 'docker', 'memory': '1g', 'cpus': 1}, 240)
    (output/'render.log').write_text(log)
    video = next((output/'media').rglob('BoundedScene.mp4'))
    info = probe(video)
    assert abs(info['duration']-30) < .1, info
    memory = json.loads((output/'memory.json').read_text())
    assert int(memory['memory.peak']) < int(memory['memory.max'])
    subprocess.run(['ffmpeg','-v','error','-threads','1','-i',str(video),'-f','null','-'],check=True,timeout=90)
    print('PASS: actual 30s 1080p encode/decode within 1GiB, peak MiB:', round(int(memory['memory.peak'])/1024**2, 1))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--docker', action='store_true');args=parser.parse_args()
    check_failure_attribution()
    check_review_evidence()
    if args.docker:check_real_encode()
