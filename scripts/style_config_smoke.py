import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeline import validate_video_constraints
from styles import list_styles, load_style


def check():
    validate_video_constraints({})
    for entry in list_styles():
        validate_video_constraints(load_style(entry["id"]).video)
    invalid = [{"layout": "unknown"}, {"theme": "blue"}, {"orientation": "square"}, {"reset_between_beats": 1}, {"exit_fade": "false"}, {"style_palette": []}, {"style_palette": {"background": "not-a-color"}}, {"style_palette": {"primary": None}}]
    for video in invalid:
        try:
            validate_video_constraints(video)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid style config accepted: " + repr(video))
    print("PASS: all registered styles valid; illegal layout/theme/orientation/flags/palette rejected before generation")


if __name__ == "__main__":
    check()
