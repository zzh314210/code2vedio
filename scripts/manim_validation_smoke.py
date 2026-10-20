"""Run with ProtectHome=true to cover production's Manim import boundary.

Optional --docker-project PATH also renders a real Chinese animation using
the same validated snippet. No model calls or credentials are needed.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import execution
from media import probe
from pipeline import validate_snippet


SNIPPET = """title = Text('权限修复验证', font='Noto Sans CJK SC', font_size=40).shift(UP * 1.5)
circle = Circle(color=BLUE).set_fill(BLUE, opacity=0.4)
self.add(title)
self.play(Create(circle), run_time=0.5)
self.wait(0.5)
"""


def check_validation():
    previous_environment = dict(os.environ)
    execution.manim_api_names.cache_clear()
    with patch.object(execution, "_run", wraps=execution._run) as child:
        validate_snippet(SNIPPET)
        validate_snippet("self.play(FadeIn(Square()))")
        assert child.call_count == 1, "Repeated validation reimported Manim"
        environment = child.call_args.args[2]
        assert "api_key" not in " ".join(environment).lower()
        assert not Path(child.call_args.args[1]).exists(), "Temporary config was not cleaned up"
    assert dict(os.environ) == previous_environment, "Worker environment was mutated"
    assert "manim" not in sys.modules, "Web worker imported Manim"
    for snippet, message in (
        ("self.add(InventedManimShape())", "Manim 没有 InventedManimShape"),
        ("import os", "禁止的Import"),
        ("self.camera.clear()", "不允许访问 self.camera"),
    ):
        try:
            validate_snippet(snippet)
        except ValueError as error:
            assert message in str(error), str(error)
        else:
            raise AssertionError("Invalid code accepted: " + snippet)
    execution.manim_api_names.cache_clear()
    with patch.object(execution, "_run", side_effect=PermissionError("blocked config")):
        try:
            validate_snippet(SNIPPET)
        except execution.RenderInfrastructureError:
            pass
        else:
            raise AssertionError("Infrastructure failure treated as valid code")
    validate_snippet(SNIPPET)  # A failed import must not poison later attempts.
    print("PASS: isolated Manim validation, cached API names, unchanged worker environment, syntax/security checks, recoverable infrastructure errors")


def check_render(project):
    project = project.resolve()
    output = project / "output"
    output.mkdir(parents=True, exist_ok=True)
    scene = output / "validation_scene.py"
    scene.write_text("from manim import *\nclass ValidationScene(Scene):\n    def construct(self):\n" +
                     "\n".join("        " + line for line in SNIPPET.splitlines()) + "\n", encoding="utf-8")
    log = execution.render_command(
        [sys.executable, "-m", "manim", "-qh", "--fps", "30", "--disable_caching",
         "--media_dir", str(output / "media"), str(scene), "ValidationScene"],
        project, output, {"backend": "docker", "memory": "1g", "cpus": 1}, 180,
    )
    (output / "render.log").write_text(log, encoding="utf-8")
    video = next((output / "media").rglob("ValidationScene.mp4"))
    info = probe(video)
    assert abs(info["duration"] - 1) < 0.1, info
    subprocess.run(["ffmpeg", "-v", "error", "-threads", "1", "-i", str(video),
                    "-f", "null", "-"], check=True, timeout=30)
    print("PASS: real Docker Chinese animation rendered and decoded:", video)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-project", type=Path)
    args = parser.parse_args()
    check_validation()
    if args.docker_project:
        check_render(args.docker_project)
