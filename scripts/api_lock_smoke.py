import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from execution import project_lock
from pipeline import VideoPipeline


def rejected(action):
    try:
        action()
    except RuntimeError as failure:
        assert "already running" in str(failure)
    else:
        raise AssertionError("Concurrent direct API access accepted")


def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline.project = root
        with patch.object(VideoPipeline, "_initialize") as initialize, patch.object(VideoPipeline, "_run", return_value="done") as run:
            with project_lock(root):
                with project_lock(root):
                    assert pipeline.run() == "done"
                run.reset_mock()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(rejected, lambda: VideoPipeline("test", {}, root / "output", project=root)).result(timeout=10)
                    pool.submit(rejected, pipeline.run).result(timeout=10)
                initialize.assert_not_called()
                run.assert_not_called()
            assert pipeline.run() == "done"
            VideoPipeline("test", {}, root / "output", project=root)
            initialize.assert_called_once()
    print("PASS: direct API initialization/run reject concurrent writers, same-thread CLI nesting works, locks release")


if __name__ == "__main__":
    check()
