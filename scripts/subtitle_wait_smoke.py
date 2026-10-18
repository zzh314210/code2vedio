import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from manim import Scene
from scene_runtime import NarratedScene


def check():
    scene = NarratedScene.__new__(NarratedScene)
    scene.renderer = SimpleNamespace(time=0)
    scene._beat_start = 0
    scene._beat_duration = 10
    scene._chrome = object()
    scene.mobjects = [scene._chrome, object()]
    scene.lesson_style = {"exit_fade": False}
    with patch.object(Scene, "wait") as wait:
        scene.wait(20)
        wait.assert_called_once_with(10, frozen_frame=False)
        wait.reset_mock()
        scene.end_beat()
        wait.assert_called_once_with(10, frozen_frame=False)
        wait.reset_mock()
        scene.renderer.time = 10
        scene.wait(1)
        scene.end_beat()
        wait.assert_not_called()
    scene.renderer.time = 0
    scene.lesson_style = {"exit_fade": True}
    from manim import Rectangle
    scene.mobjects = [scene._chrome, Rectangle()]
    with patch.object(Scene, "wait") as wait, patch.object(Scene, "play") as play:
        scene.end_beat()
        wait.assert_called_once_with(9.7, frozen_frame=False)
        assert play.call_args.kwargs["run_time"] == 0.3
    print("PASS: ordinary wait, final hold and exit-fade hold keep subtitle updates active; exhausted beat skips waits")


if __name__ == "__main__":
    check()
