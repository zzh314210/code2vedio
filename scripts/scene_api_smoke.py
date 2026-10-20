"""Regression coverage for model-invented helper arguments and archived APIs."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from pipeline import VideoPipeline, validate_snippet
from scene_api import reference

for code, expected in [
    ('self.sketch_shape("rounded_rect", width=7.2, fill_color=self.style_color("panel"))', 'fill_color'),
    ('self.sketch_shape("rectangle", corner_radius=.2)', 'corner_radius'),
    ('self.sketch_shape("rounded_rect")', 'RoundedRectangle'),
    ('self.sketch_shape("circle")', 'ellipse'),
    ('self.scene_text("title", stroke_width=2)', 'stroke_width'),
    ('self.sketch_line([0,0,0])', 'end'),
    ('self.ink_path([[0,0],[1,1]], **options)', '*args/**kwargs'),
]:
    try:
        validate_snippet(code)
    except ValueError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError('Invalid custom API call accepted: ' + code)

for code in [
    'self.add(RoundedRectangle(width=7.2, height=3, corner_radius=.16, fill_color=self.style_color("panel"), stroke_width=2))',
    'shape = self.sketch_shape("rectangle", width=3, fill=self.style_color("panel"))\nshape.set_stroke(width=2)',
    'self.sketch_shape("arrow", points=[[0,0],[1,1]], color=self.style_color("primary"))',
    'self.scene_text("标题", 30)\nself.scene_paragraph("正文", width=5)',
]:
    validate_snippet(code)
assert 'fill=None' in reference() and 'RoundedRectangle' in reference()
assert 'manim' not in sys.modules, 'API contract imported the rendering runtime'

with tempfile.TemporaryDirectory() as temporary:
    runtime = Path(temporary)
    (runtime / 'scene_runtime.py').write_text('class NarratedScene:\n    def scene_text(self, text): pass\n')
    validate_snippet('self.scene_text("title")', runtime=runtime)
    try:
        validate_snippet('self.scene_text("title", font_size=30)', runtime=runtime)
    except ValueError as error:
        assert 'font_size' in str(error)
    else:
        raise AssertionError('Archived API replaced by current API')
    try:
        validate_snippet('self.scene_paragraph("title", width=5)', runtime=runtime)
    except ValueError as error:
        assert '当前项目未提供 self.scene_paragraph' in str(error)
    else:
        raise AssertionError('Missing archived helper accepted')
    assert 'font_size' not in reference(runtime)

with tempfile.TemporaryDirectory() as temporary:
    pipe = VideoPipeline.__new__(VideoPipeline)
    pipe.output = Path(temporary)
    pipe.config = {'video': {'fix_attempts': 0}}
    pipe.render = Mock(side_effect=RuntimeError('Render exited with code 1:\nTypeError: unsupported fill_color'))
    try:
        pipe.render_with_repairs({'id':'section_1','title':'测试章节'}, {'beats':[]}, 0)
    except RuntimeError as error:
        assert 'unsupported fill_color' in str(error) and '测试章节' in str(error)
    else:
        raise AssertionError('Failed render accepted')
print('PASS: helper signatures, enum values, valid drawing APIs, archived runtime contracts, and actionable render errors')
