import copy
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent import main
from configuration import DEFAULTS, merge, resolve_config
from materials import load_materials
from narration import register_tts_provider, Narrator
from pipeline import VideoPipeline
from styles import load_style, list_styles, style_video_config
from video_project import initialize_project


class FakeGateway:
    calls = 0
    image_calls = 0

    def __init__(self, *args, **kwargs):
        self.usage = {}

    def json(self, prompt, validator, **kwargs):
        FakeGateway.calls += 1
        if kwargs.get("images"):
            FakeGateway.image_calls += 1
        if "阶段: OUTLINE" in prompt:
            value = {"topic": "产品介绍", "target_audience": "用户", "warnings": [], "sections": [{"id": "section_1", "title": "产品", "goal": "介绍", "key_points": ["功能"], "sources": []}]}
        else:
            value = {"sections": [{"id": "section_1", "title": "产品", "beats": [{"narration": "介绍产品功能。", "caption": "产品功能", "visual": "展示产品"}]}]}
        validator(value)
        return value


def run():
    config = resolve_config(merge(DEFAULTS, {"style": "infographic", "text": {"model": "fake", "api_key": "secret-test-key"}, "tts": {"provider": "none"}}))
    assert len(list_styles()) >= 5
    customized = merge(config, {"video_overrides": {"orientation": "portrait", "brand": "Custom brand", "style_palette": {"primary": "#123456"}}})
    styled = style_video_config(customized, load_style("infographic"))
    assert styled["video"]["orientation"] == "portrait"
    assert styled["video"]["brand"] == "Custom brand"
    assert styled["video"]["style_palette"]["primary"] == "#123456"
    assert style_video_config(styled, load_style("infographic")) == styled
    try:
        load_style("../default")
    except ValueError:
        pass
    else:
        raise AssertionError("Style traversal accepted")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        reference = root / "picture.png"
        from PIL import Image
        Image.new("RGB", (32, 32), "blue").save(reference)
        text = root / "brief.txt"
        text.write_text("产品设计参考", encoding="utf-8")
        inputs = load_materials([text], "产品", config["materials"], references=[reference])
        assert inputs["visual_inputs"][0]["type"] == "image"
        assert "产品设计参考" in inputs["context"]
        audio_reference = root / "reference.wav"
        audio_reference.write_bytes(b"mock-audio")
        transcription = {"enabled": True, "base_url": "https://transcription.example/v1", "api_key": "transcription-test-secret", "model": "test-transcriber"}
        audio_settings = merge(config["materials"], {"transcription": transcription})
        with patch("audio_references.OpenAI") as client_factory:
            client_factory.return_value.audio.transcriptions.create.return_value = SimpleNamespace(text="Audio reference product facts")
            first = load_materials([], "product", audio_settings, references=[audio_reference], cache_directory=root / "transcripts")
            second = load_materials([], "product", audio_settings, references=[audio_reference], cache_directory=root / "transcripts")
            assert "Audio reference product facts" in first["context"]
            assert second == first
            assert client_factory.return_value.audio.transcriptions.create.call_count == 1
            assert "transcription-test-secret" not in next((root / "transcripts").glob("*.json")).read_text(encoding="utf-8")
        project = root / "video"
        with patch("pipeline.ModelGateway", FakeGateway):
            pipeline = VideoPipeline("介绍新产品", config, project / "output", project=project, references=[reference])
            from styles import style_stage_policy
            assert style_stage_policy(pipeline.style, "code") in pipeline.prompt("code", "test")
            from styles import snapshot_hash
            snapshot = pipeline.style.snapshot()
            assert snapshot["content_hash"] == snapshot_hash(snapshot)
            for stage in ("outline", "storyboard", "code", "review"):
                assert snapshot["technical"][stage] in pipeline.prompt(stage, "test")
            assert pipeline.config["video"]["layout"] == "minimal"
            pipeline.run(plan_only=True)
            assert FakeGateway.image_calls >= 2, "Reference images did not reach planning requests"
            section = {"id": "image_render", "title": "Image reference", "beats": [{"duration": 0.6, "caption": "Image", "narration": "Image", "visual": "Image"}], "assets": [{"key": "photo", "path": str(project / "input/references/picture.png"), "credit": "User image"}]}
            pipeline.config["video"].update(quality="low", fps=15)
            video = pipeline.render(section, {"beats": [{"code": 'self.add(self.asset("photo"))'}]}, 0)
            assert video.is_file(), "Reference image did not render"
            video_project = root / "video-reference"
            video_pipeline = VideoPipeline("Describe reference video", config, video_project / "output", project=video_project, references=[video])
            assert len(video_pipeline.reference_images) == 3
            assert all(frame.is_file() for frame in video_pipeline.reference_images)
            video_pipeline.run(plan_only=True)
            before = FakeGateway.calls
            VideoPipeline("介绍新产品", config, project / "output", project=project, resume=True).run(plan_only=True)
            assert FakeGateway.calls == before
            assert (project / "input/references/picture.png").is_file()
            assert not (project / "examples").exists()
            assert "secret-test-key" not in (project / "settings.json").read_text(encoding="utf-8")
            task = root / "task.json"
            task.write_text(json.dumps({"prompt": "介绍产品", "style": "presentation", "references": ["picture.png"]}), encoding="utf-8")
            destination = root / "cli"
            assert main(["--task-file", str(task), "--project", str(destination), "--plan-only", "--tts-provider", "none"]) == 0
            saved = json.loads((destination / "task.json").read_text(encoding="utf-8"))
            assert saved["references"] == ["input/references/picture.png"]
            assert main(["--project", str(destination), "--resume", "--plan-only"]) == 0
        class TestProvider:
            def __init__(self, settings):
                pass

            def synthesize(self, text, destination):
                return {"duration": 1, "provider": "test"}
        register_tts_provider("test", TestProvider)
        assert Narrator({"provider": "test"}).synthesize("test", root / "test.wav")["provider"] == "test"
    print("CLI smoke passed: task, references, styles, resume, redaction, TTS registry")


if __name__ == "__main__":
    run()
