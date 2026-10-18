import hashlib
import json
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from configuration import DEFAULTS, merge, resolve_config
from media import probe
from pipeline import VideoPipeline
from smoke import COUNTS, MockService


def tree_digest(directory):
    return {file.relative_to(directory).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in directory.rglob("*") if file.is_file()}


def run():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockService)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    COUNTS.clear()
    base = f"http://127.0.0.1:{server.server_port}"
    config = resolve_config(merge(DEFAULTS, {
        "text": {"api_key": "dummy-relocation", "base_url": base + "/v1", "model": "smoke-model", "max_retries": 0},
        "vision": {"enabled": True, "rounds": 1, "frames": 2},
        "tts": {"provider": "http", "url": base + "/http-speech", "payload": {"text": "{text}"}},
        "video": {"quality": "low", "fps": 15, "max_sections": 1, "max_beats": 1},
        "assets": {"enabled": False}}))
    try:
        with tempfile.TemporaryDirectory(prefix="c2v-relocation-") as temporary:
            root = Path(temporary)
            material = root / "brief.txt"
            material.write_text("100 and 120: compare quantities.", encoding="utf-8")
            reference = root / "picture.png"
            from PIL import Image
            Image.new("RGB", (32, 32), "blue").save(reference)
            svg = root / "symbol.svg"
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>', encoding="utf-8")
            original = root / "original"
            pipeline = VideoPipeline("Compare quantities", config, original / "output",
                                     [material], project=original, references=[reference, svg])
            pipeline.run()
            archived_assets = json.loads((original / "output/storyboard_assets.json").read_text(encoding="utf-8"))["sections"][0]["assets"]
            assert any(item["key"].startswith("local_reference_") for item in archived_assets)
            assert len(list((original / "assets/local").glob("reference_*.svg"))) == 1
            before = tree_digest(original)
            counts = dict(COUNTS)
            copied = root / "copied"
            shutil.copytree(original, copied)
            manifest_file = copied / "output/manifest.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest.pop("output_directory")
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            with patch("pipeline.load_style", side_effect=AssertionError("Global styles must not be loaded")), \
                    patch.object(VideoPipeline, "render", side_effect=AssertionError("Cached render must be reused")), \
                    patch("pipeline.Narrator.synthesize", side_effect=AssertionError("Cached audio must be reused")):
                resumed = VideoPipeline("Compare quantities", config, copied / "output", project=copied, resume=True)
                final = resumed.run()
            assert COUNTS == counts
            assert tree_digest(original) == before
            assert final.is_relative_to(copied)
            assert {"video", "audio", "subtitle"} <= {item["type"] for item in probe(final)["streams"]}
            for filename in (copied / "output").rglob("*.json"):
                assert str(original).replace("\\", "\\\\") not in filename.read_text(encoding="utf-8"), filename
            snapshot = json.loads((copied / "prompts/style.json").read_text(encoding="utf-8"))
            assert snapshot["stages"]["code"] in resumed.prompt("code", "test")
            settings = {"music": {"source": "brief.txt", "volume": 0.15}}
            resumed.config["montage"] = settings
            def compose(video, audio, destination_video, destination_audio, duration, passed_settings, sources):
                assert passed_settings == settings
                assert all(Path(source["path"]).is_relative_to(copied) for source in sources)
                shutil.copy2(video, destination_video)
                shutil.copy2(audio, destination_audio)
                return destination_video, destination_audio
            with patch.dict(sys.modules, {"montage": SimpleNamespace(compose_media=compose)}):
                resumed.run()
            resumed.config["montage"] = {}
            with patch.dict(sys.modules, {"montage": SimpleNamespace(compose_media=lambda *args: (_ for _ in ()).throw(AssertionError("Empty settings must skip montage")))}):
                resumed.run()
            assert tree_digest(original) == before
            unsafe = root / "unsafe"
            shutil.copytree(original, unsafe)
            cache = unsafe / "output/reviewed.json"
            data = json.loads(cache.read_text(encoding="utf-8"))
            data["section_1"]["video"] = str(root / "outside.mp4")
            cache.write_text(json.dumps(data), encoding="utf-8")
            try:
                VideoPipeline("Compare quantities", config, unsafe / "output", project=unsafe, resume=True)
            except ValueError as failure:
                assert "outside" in str(failure)
            else:
                raise AssertionError("External cached path accepted")
            assert tree_digest(original) == before
            missing = root / "missing"
            shutil.copytree(original, missing)
            cached_video = json.loads((missing / "output/rendered.json").read_text(encoding="utf-8"))["section_1"]["video"]
            (missing / Path(cached_video).relative_to(original)).unlink()
            VideoPipeline("Compare quantities", config, missing / "output", project=missing, resume=True)
            assert not (missing / "output/reviewed.json").exists()
            assert json.loads((missing / "output/rendered.json").read_text(encoding="utf-8")) == {}
        print("Relocation smoke passed: real copy, cached render/audio/review/assets, standalone style, safe paths, montage integration")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()
