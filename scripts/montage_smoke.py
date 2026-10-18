import sys
import tempfile
from pathlib import Path

import av

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media import ffmpeg_binary, mux, probe, run_command, silence
from montage import compose_media
from task_schema import reference_record


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        base, footage = root / "base.mp4", root / "footage.mp4"
        audio, music = root / "audio.wav", root / "music.wav"
        for destination, color in ((base, "blue"), (footage, "red")):
            run_command([ffmpeg_binary(), "-y", "-f", "lavfi", "-i",
                         f"color=c={color}:s=160x90:r=15:d=2", "-c:v", "libx264",
                         "-pix_fmt", "yuv420p", str(destination)])
        silence(audio, 2)
        run_command([ffmpeg_binary(), "-y", "-f", "lavfi", "-i",
                     "sine=frequency=440:duration=1", str(music)])
        sources = [reference_record(footage), reference_record(music)]
        assert compose_media(base, audio, root / "unused.mp4", root / "unused.wav", 2, {}, sources) == (base, audio)
        settings = {"clips": [{"source": "footage.mp4", "start": 0.5, "duration": 0.8}],
                    "music": {"source": "music.wav", "volume": 0.2}}
        video, mixed = compose_media(base, audio, root / "montage.mp4", root / "mixed.wav", 2, settings, sources)
        assert abs(probe(video)["duration"] - 2) < 0.1
        assert abs(probe(mixed)["duration"] - 2) < 0.1
        with av.open(str(video)) as container:
            frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
        assert frames[2][:, :, 2].mean() > 200
        assert frames[12][:, :, 0].mean() > 200
        assert frames[25][:, :, 2].mean() > 200
        with av.open(str(mixed)) as container:
            assert any(abs(frame.to_ndarray()).max() > 0 for frame in container.decode(audio=0))
        subtitles = root / "subtitles.srt"
        subtitles.write_text("1\n00:00:00,000 --> 00:00:02,000\nTest\n", encoding="utf-8")
        mux(video, mixed, subtitles, root / "final.mp4", 2)
        assert {stream["type"] for stream in probe(root / "final.mp4")["streams"]} == {"video", "audio", "subtitle"}
        for invalid in ({"clips": [{"source": "../unknown.mp4", "duration": 1}]},
                        {"clips": [{"source": "footage.mp4", "start": 1.5, "duration": 1}]},
                        {"music": {"source": "music.wav", "volume": 2}}):
            try:
                compose_media(base, audio, root / "bad.mp4", root / "bad.wav", 2, invalid, sources)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid montage accepted")
    print("Montage smoke passed: footage pixels, music, duration, subtitles, validation")


if __name__ == "__main__":
    run()
