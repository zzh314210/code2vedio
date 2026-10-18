import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import VideoPipeline


def check():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = root / "current"
        project.mkdir()
        outside = root / "other"
        outside.mkdir()
        sentinel = outside / "style.json"
        sentinel.write_text("not valid JSON; must never be read", encoding="utf-8")
        link = project / "prompts"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            for resume in (False, True):
                with patch("pipeline.load_style", side_effect=AssertionError("Style loading must not start")):
                    try:
                        VideoPipeline("test", {"style": "default"}, project / "output", project=project, resume=resume)
                    except ValueError as failure:
                        assert "escapes" in str(failure)
                    else:
                        raise AssertionError("External style snapshot accepted")
            assert sentinel.read_text(encoding="utf-8") == "not valid JSON; must never be read"
            assert not (project / "output").exists()
        finally:
            link.rmdir() if os.name == "nt" else link.unlink()
    print("PASS: new and resumed tasks reject cross-project style directory before reading snapshot or initializing outputs")


if __name__ == "__main__":
    check()
