"""Render Chinese text, LaTeX and Rough.js through the production Docker backend."""
import shutil
import av
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from configuration import load_config
from execution import render_command
from media import probe

project = ROOT / '.tmp/deployment-render'
runtime = project / 'code/runtime'
runtime.mkdir(parents=True, exist_ok=True)
for name in ('handdrawn_runtime.py', 'handdrawn_bridge.cjs'):
    shutil.copy2(ROOT / 'src' / name, runtime / name)
shutil.copytree(ROOT / 'src/vendor', runtime / 'vendor', dirs_exist_ok=True)
output = project / 'output'
output.mkdir(exist_ok=True)
script = output / 'deployment_scene.py'
script.write_text('''from manim import *
from handdrawn_runtime import sketch_shape

class Palette:
    def style_color(self, name):
        return '#58C4DD'

class DeploymentScene(Scene):
    def construct(self):
        title = Text('视频工作台部署验证', font='Noto Sans CJK SC', font_size=44).shift(UP * 2)
        formula = MathTex(r'E=mc^2').shift(DOWN)
        shape = sketch_shape(Palette(), 'rectangle', width=3, height=1, fill='#224466')
        self.add(title, formula, shape)
        self.wait(0.4)
''')
settings = load_config(ROOT / 'config.local.json')['execution']
assert settings['backend'] == 'docker'
log = render_command([sys.executable, '-m', 'manim', '-qh', '--fps', '30', '--disable_caching', '--media_dir', str(output / 'media'), str(script), 'DeploymentScene'], project, output, settings, 180)
(output / 'render.log').write_text(log)
video = next((output / 'media/videos').rglob('DeploymentScene.mp4'))
info = probe(video)
with av.open(str(video)) as container:
    stream = container.streams.video[0]
    assert (stream.width, stream.height) == (1920, 1080)
    assert float(stream.average_rate) == 30
assert info['duration'] > 0
print('PASS: production Docker backend rendered 1080p Chinese text, LaTeX and offline Rough.js; media:', video)
