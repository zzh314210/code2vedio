import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import VideoPipeline


def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        project = root / "current"
        output = project / "output"
        output.mkdir(parents=True)
        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline.project = project
        pipeline.output = output
        outside = root / "other/audio.wav"
        outside.parent.mkdir()
        outside.write_bytes(b"other-project-sentinel")
        cache = output / "timing.json"
        cache.write_text(json.dumps({"audio": str(outside)}), encoding="utf-8")
        before = cache.read_bytes()
        try:
            pipeline.relocate_caches({})
        except ValueError as failure:
            assert "outside" in str(failure)
        else:
            raise AssertionError("Legacy cache bypassed project boundary")
        assert cache.read_bytes() == before
        assert outside.read_bytes() == b"other-project-sentinel"
        local = output / "audio.wav"
        local.write_bytes(b"current-project")
        cache.write_text(json.dumps({"audio": str(local)}), encoding="utf-8")
        pipeline.relocate_caches({})
        assert json.loads(cache.read_text())["audio"] == str(local.resolve())
    print("PASS: legacy cache without project root still validates media paths; cross-project references rejected without writes")


if __name__ == "__main__":
    check()
