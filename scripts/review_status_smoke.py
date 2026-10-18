import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import review_summary


def check():
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        rendered = {"section_1": {"revision": 1}}
        feedback = output / "section_1_review_0.json"
        for value, expected in (({"has_issues": False}, "unverified"), ({"has_issues": False, "reviewed_revision": 0}, "unverified"), ({"has_issues": True, "reviewed_revision": 1}, "issues_found"), ({"has_issues": False, "reviewed_revision": 1}, "passed")):
            feedback.write_text(json.dumps(value), encoding="utf-8")
            summary = review_summary(output, rendered, True)
            assert summary["sections"]["section_1"]["status"] == expected
            assert summary["passed"] == (expected == "passed")
        assert review_summary(output, rendered, False)["sections"]["section_1"]["status"] == "disabled"
    print("PASS: exact revision verdict binding; legacy and post-repair artifacts not falsely approved")


if __name__ == "__main__":
    check()
