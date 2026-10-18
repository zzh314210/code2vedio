import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from configuration import DEFAULTS, merge, public_config, resolve_config
from media import probe
from pipeline import VideoPipeline, save_json


def wav_file(filename):
    filename.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(filename), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\x01\x00' * 48000)


def make_pipeline(project):
    config = resolve_config(merge(DEFAULTS, {
        'text': {'api_key': 'dummy-local-only', 'model': 'mock', 'base_url': 'http://127.0.0.1:1/v1'},
        'vision': {'enabled': False}, 'tts': {'provider': 'none'},
        'assets': {'enabled': False}, 'video': {'pause_seconds': 0, 'fps': 30}}))
    gateway = SimpleNamespace(usage={}, json=Mock(side_effect=AssertionError('API forbidden')))
    narrator = SimpleNamespace(synthesize=Mock(side_effect=AssertionError('TTS forbidden')))
    with patch('pipeline.ModelGateway', return_value=gateway), patch('pipeline.Narrator', return_value=narrator):
        return VideoPipeline('Local regression', config, project / 'output', project=project)


def check_style(pipeline):
    snapshot = json.loads((pipeline.project / 'prompts/style.json').read_text(encoding='utf-8'))
    assert pipeline.style_snapshot == snapshot
    stages = ('outline', 'storyboard', 'code', 'review')
    before = {stage: pipeline.prompt(stage, 'base') for stage in stages}
    with patch('pipeline.style_stage_policy', return_value='GLOBAL STYLE CHANGED') as global_policy:
        for stage in stages:
            assert pipeline.prompt(stage, 'base') == before[stage]
            assert snapshot['stages'][stage] in before[stage]
            assert snapshot['technical'][stage] in before[stage]
        global_policy.assert_not_called()
    print('PASS: new task binds saved snapshot; all stages ignore global policy changes')


def check_audio(pipeline):
    audio = pipeline.output / 'audio/section_1_01.wav'
    wav_file(audio)
    text = 'Real duration, incorrect metadata'
    fingerprint = hashlib.sha256(json.dumps({'text': text, 'tts': public_config(pipeline.config['tts']), 'subtitle_version': 2}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    save_json(audio.with_suffix('.json'), {'duration': 0.1, 'fingerprint': fingerprint})
    section = {'id': 'section_1', 'title': 'Safety', 'beats': [{'narration': text, 'caption': 'Safety', 'visual': 'Vector'}]}
    pipeline.prepare_audio(section)
    assert abs(probe(audio)['duration'] - 2) < 0.001
    assert section['beats'][0]['duration'] == 2
    assert json.loads(audio.with_suffix('.json').read_text())['duration'] == 2
    pipeline.narrator.synthesize.assert_not_called()
    audio.unlink()
    audio.with_suffix('.json').unlink()
    def synthesize(text, destination):
        wav_file(destination)
        return {'duration': 0.1}
    pipeline.narrator.synthesize = Mock(side_effect=synthesize)
    pipeline.prepare_audio(section)
    assert section['beats'][0]['duration'] == 2
    assert json.loads(audio.with_suffix('.json').read_text())['duration'] == 2
    storyboard = {'sections': [section]}
    outline = {'warnings': []}
    def cached(name, *arguments):
        return copy.deepcopy(outline if name == 'outline.json' else storyboard if name == 'storyboard.json' else {'beats': [{'code': 'self.wait(1)'}]})
    pipeline.config['video']['target_duration'] = 1
    with patch.object(pipeline, 'cached_json', side_effect=cached):
        try:
            pipeline.run(stop_after='audio')
        except ValueError as failure:
            assert 'never truncate' in str(failure)
        else:
            raise AssertionError('Short target accepted real longer speech')
    pipeline.config['video']['target_duration'] = 3
    with patch.object(pipeline, 'cached_json', side_effect=cached):
        pipeline.run(stop_after='audio')
    assert json.loads((pipeline.output / 'timing.json').read_text())['sections'][0]['beats'][0]['duration'] == 3
    stale = copy.deepcopy(storyboard)
    stale['sections'][0]['beats'][0]['duration'] = 0.1
    save_json(pipeline.output / 'storyboard_assets.json', stale)
    video = pipeline.output / 'cached.mp4'
    video.touch()
    rendered = {'section_1': {'video': str(video), 'revision': 0}}
    save_json(pipeline.output / 'rendered.json', rendered)
    save_json(pipeline.output / 'reviewed.json', rendered)
    with patch.object(pipeline, 'cached_json', side_effect=cached), patch('pipeline.fit_audio') as fit, patch('pipeline.mux') as mux:
        try:
            pipeline.run()
        except ValueError as failure:
            assert 'refusing to truncate' in str(failure)
        else:
            raise AssertionError('Compose accepted stale shorter beat')
        fit.assert_not_called()
        mux.assert_not_called()
    print('PASS: real WAV overrides cached/plugin duration, short target rejected, longer target padded, compose refuses truncation')


def link_directory(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError as failure:
        if os.name != 'nt':
            raise
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True, text=True)
        if result.returncode == 0:
            return True
        print('SKIP: Windows directory symlink/junction unavailable:', failure, result.stderr.strip())
        return False


def check_paths(root):
    outside = root / 'other-project'
    outside.mkdir()
    sentinel = outside / 'sentinel.txt'
    sentinel.write_bytes(b'unchanged')
    tested = 0
    for kind in ('revision', 'source', 'script', 'log'):
        pipeline = make_pipeline(root / ('paths-' + kind))
        directory = pipeline.output / 'section_1/revision_0'
        if kind == 'revision':
            directory.parent.mkdir(parents=True)
            link = directory
        elif kind == 'source':
            link = pipeline.project / 'code/manim'
        else:
            directory.mkdir(parents=True)
            link = directory / ('scene.py' if kind == 'script' else 'render.log')
        if kind in ('revision', 'source'):
            if not link_directory(link, outside):
                continue
        else:
            try:
                link.symlink_to(sentinel)
            except OSError as failure:
                if os.name != 'nt':
                    raise
                print('SKIP: Windows file symlink unavailable for', kind, ':', failure)
                continue
        before = {file.name: file.read_bytes() for file in outside.iterdir()}
        with patch.object(pipeline, 'assemble_code', return_value='pass\n'), patch('execution.render_command', return_value='mock log') as execute:
            try:
                pipeline.render({'id': 'section_1'}, {}, 0)
            except ValueError as failure:
                assert 'escapes' in str(failure)
            else:
                raise AssertionError('Linked output accepted: ' + kind)
            if kind != 'log':
                execute.assert_not_called()
        assert before == {file.name: file.read_bytes() for file in outside.iterdir()}
        link.unlink() if kind in ('script', 'log') or link.is_symlink() else link.rmdir()
        tested += 1
    print('PASS: linked render writes refused without changing other project; cases=' + str(tested) + '/4 (see explicit SKIP messages)')


def check():
    with tempfile.TemporaryDirectory(prefix='c2v-style-safety-') as temporary:
        root = Path(temporary)
        pipeline = make_pipeline(root / 'main')
        check_style(pipeline)
        check_audio(pipeline)
        check_paths(root)
    print('PASS: style safety regressions; no remote APIs; Docker not exercised')


if __name__ == '__main__':
    check()
