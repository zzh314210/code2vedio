import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import validate_snippet
from scene_runtime import NarratedScene
from styles import load_style, snapshot_hash


def check():
    package = load_style("handdrawn")
    snapshot = package.snapshot()
    assert snapshot["version"] == "1.0.0"
    assert snapshot["content_hash"] == snapshot_hash(snapshot)
    assert snapshot["video"]["layout"] == "canvas"
    assert snapshot["video"]["style_palette"]["background"] == "#FFF9ED"
    for stage in ("outline", "storyboard", "code", "review"):
        assert "self.sketch_line" in snapshot["stages"][stage]
        assert snapshot["technical"][stage].strip()
    validate_snippet("stroke = self.sketch_line([0,0,0], [2,1,0], arrow=True)\nself.play(Create(stroke))")
    scene = NarratedScene()
    first = scene.sketch_line([0, 0, 0], [2, 1, 0], arrow=True)
    second = scene.sketch_line([0, 0, 0], [2, 1, 0], arrow=True)
    assert len(first) == 4
    for actual, repeated in zip(first, second):
        np.testing.assert_array_equal(actual.points, repeated.points)
        assert np.isfinite(actual.points).all()
    np.testing.assert_allclose(first[0].get_start(), [0, 0, 0])
    np.testing.assert_allclose(first[0].get_end(), [2, 1, 0])
    for start, end, width in (([0, 0, 0], [0, 0, 0], 3), ([0, 0], [1, 1], 3), ([0, 0, 0], [float("nan"), 1, 0], 3), ([0, 0, 0], [1, 1, 0], 0)):
        try:
            scene.sketch_line(start, end, width=width)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid sketch geometry accepted")
    print("PASS: handdrawn version/hash, four stage policies, canvas palette, allowed API, deterministic strokes, exact endpoints, invalid geometry rejected")


if __name__ == "__main__":
    check()
