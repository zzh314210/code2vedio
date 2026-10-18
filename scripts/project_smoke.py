import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from configuration import merge, resolve_config
from media import mux
from pipeline import VideoPipeline, validate_code, validate_snippet, validate_video_constraints
from project_extensions import read_extensions
from video_project import apply_project_pack, initialize_project, project_pack_config, read_templates, write_json


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rejected(action, message):
    try:
        action()
    except ValueError:
        return
    raise RuntimeError(message)


def check_video_constraints(config):
    pipeline = object.__new__(VideoPipeline)
    pipeline.config = copy.deepcopy(config)
    pipeline.config["video"].update(narration_max_chars=200, caption_max_chars=80)
    pipeline.config["course"] = {"language": "测试语言"}
    pipeline.extensions = {}
    from styles import load_style
    pipeline.style = load_style("default")
    pipeline.topic = "测试"
    pipeline.config["task"] = pipeline.config["course"]
    validate_video_constraints(pipeline.config["video"])
    outline = {"sections": [{"id": "section_1"}]}
    beat = {"narration": "文" * 200, "caption": "字" * 80, "visual": "比较数量"}
    storyboard = {"sections": [{"id": "section_1", "title": "数量比较", "beats": [beat]}]}
    pipeline.validate_storyboard(storyboard, outline)
    for field, limit in (("narration", 200), ("caption", 80)):
        invalid = copy.deepcopy(storyboard)
        invalid["sections"][0]["beats"][0][field] += "超"
        rejected(lambda: pipeline.validate_storyboard(invalid, outline), f"{field} 未遵守配置上限 {limit}")
    for stage in ("outline", "storyboard", "code", "review"):
        require("项目语言：测试语言" in pipeline.prompt(stage, "测试"), "课程语言未注入 " + stage)
    prompt = pipeline.prompt("storyboard", "测试")
    require("narration ≤200" in prompt and "caption ≤80" in prompt, "分镜提示词未注入实际字符上限")
    for key in ("narration_max_chars", "caption_max_chars"):
        pipeline.config["video"].pop(key)
        for invalid in (True, 0, 4001, "140"):
            rejected(lambda: validate_video_constraints({key: invalid}), "接受了无效字符上限")
    pipeline.config["video"].pop("subtitle_language", None)
    validate_video_constraints(pipeline.config["video"])
    beat.update(narration="文" * 140, caption="字" * 42)
    pipeline.validate_storyboard(storyboard, outline)
    for field in ("narration", "caption"):
        invalid = copy.deepcopy(storyboard)
        invalid["sections"][0]["beats"][0][field] += "超"
        rejected(lambda: pipeline.validate_storyboard(invalid, outline), "旧配置默认上限失效")
    rejected(lambda: validate_video_constraints({"subtitle_language": "invalid"}), "接受了无效字幕语言代码")
    with patch("media.run_command") as command, patch("media.ffmpeg_binary", return_value="ffmpeg"), patch("media.av.open") as media_input:
        media_input.return_value.__enter__.return_value.streams = [SimpleNamespace(type="video", base_rate=30, average_rate=30)]
        mux("video.mp4", "audio.wav", "subtitles.srt", "final.mp4", 1, "eng")
        require("language=eng" in command.call_args.args[0], "自定义字幕语言未传给 FFmpeg")
        mux("video.mp4", "audio.wav", "subtitles.srt", "final.mp4", 1)
        require("language=zho" in command.call_args.args[0], "默认字幕语言发生变化")


def check_projects(config, directory):
    check_video_constraints(config)
    neutral = directory / "neutral-project"
    initialize_project(neutral, "数量比较", config)
    runtime = neutral / "code/runtime"
    require(read_extensions(runtime) == {}, "空白项目意外注册了专题扩展")
    require({file.name for file in runtime.iterdir()} == {"scene_runtime.py", "project_extensions.py", "extensions.json"}, "空白项目夹带专题运行时代码")
    require(not any(word in "\n".join(read_templates(neutral).values()) for word in ("公务员", "考公", "牛吃草", "cow_grass")), "通用模板含有领域定制")

    pack = directory / "neutral-pack"
    (pack / "prompts").mkdir(parents=True)
    (pack / "materials").mkdir()
    (pack / "code/runtime/extensions").mkdir(parents=True)
    (pack / "prompts/policy.txt").write_text(read_templates(neutral)["policy"] + "\nPACK_POLICY_ONLY", encoding="utf-8")
    (pack / "materials/bundled.md").write_text("# 数量比较\nPACK_MATERIAL_ONLY：两组数量分别为100和120。", encoding="utf-8")
    write_json(pack / "course.json", {"course": {"instructions": "PACK_COURSE_ONLY"}, "video": {"brand": "PACK_BRAND_ONLY", "theme": "light"}})
    manifest = {"smoke_visual": {"file": "extensions/visual.py", "entrypoint": "animate", "description": "数量比较的可信测试图形"}}
    write_json(pack / "code/runtime/extensions.json", manifest)
    (pack / "code/runtime/scene_runtime.py").write_text("raise RuntimeError('must not replace shared runtime')", encoding="utf-8")
    (pack / "code/runtime/extensions/visual.py").write_text(
        "import importlib.util\nfrom manim import Dot\n\ndef animate(scene, index):\n"
        "    assert index == 0\n"
        "    assert importlib.util.find_spec('video_project') is None\n"
        "    assert importlib.util.find_spec('inherited_path_sentinel') is None\n"
        "    scene.add(Dot())\n", encoding="utf-8")
    settings = resolve_config(merge(config, merge(project_pack_config(pack), {"vision": {"enabled": False}})))
    project = directory / "extension-project"
    initialize_project(project, "数量比较", settings)
    apply_project_pack(pack, project)
    require((project / "code/runtime/scene_runtime.py").read_bytes() == (neutral / "code/runtime/scene_runtime.py").read_bytes(), "包替换了通用运行时")
    registry = read_extensions(project / "code/runtime")
    validate_snippet('self.extension("smoke_visual", 0)', registry)
    validate_code({"beats": [{"code": 'self.extension("smoke_visual", 0)'}]}, 1, registry)
    for snippet in ('self.extension("unknown", 0)', 'name = "smoke_visual"; self.extension(name)', 'callback = self.extension; callback("smoke_visual")', 'self.cow_grass(0)'):
        rejected(lambda: validate_snippet(snippet, registry), "接受了非法扩展调用: " + snippet)
    target = runtime / "extensions.json"
    for entry in (
        {"file": "../visual.py", "entrypoint": "animate"},
        {"file": "C:/visual.py", "entrypoint": "animate"},
        {"file": "extensions\\visual.py", "entrypoint": "animate"},
        {"file": "extensions/missing.py", "entrypoint": "animate"},
        {"file": "scene_runtime.py", "entrypoint": "animate"},
    ):
        write_json(target, {"bad": entry})
        rejected(lambda: read_extensions(runtime), "接受了非法扩展清单")
    write_json(target, {})
    write_json(pack / "course.json", {"text": {"api_key": "must-not-import"}})
    rejected(lambda: project_pack_config(pack), "包能注入服务或凭证配置")
    write_json(pack / "course.json", {"course": {"instructions": "PACK_COURSE_ONLY"}, "video": {"brand": "PACK_BRAND_ONLY", "theme": "light"}})

    output = project / "output"
    pipeline = VideoPipeline("数量比较", settings, output, [project / "input/materials/bundled.md"], project=project)
    require("PACK_MATERIAL_ONLY" in pipeline.materials["context"], "项目包教材未读入")
    require("smoke_visual" in pipeline.prompt("code", "代码阶段"), "扩展未注入代码提示词")
    pipeline.run(stop_after="storyboard")
    VideoPipeline("数量比较", settings, output, resume=True, project=project).run(stop_after="storyboard")
    section = {"id": "section_extension", "title": "项目内扩展", "beats": [{"duration": 0.6, "narration": "这是数量比较图形。", "caption": "项目内可信图形", "visual": "圆点"}]}
    sentinel = directory / "inherited-imports"
    sentinel.mkdir()
    (sentinel / "inherited_path_sentinel.py").write_text("SENTINEL = True\n", encoding="utf-8")
    old_path, old_safe = os.environ.get("PYTHONPATH"), os.environ.get("PYTHONSAFEPATH")
    os.environ["PYTHONPATH"] = str(sentinel) + os.pathsep + str(Path(__file__).resolve().parents[1] / "src")
    try:
        parent_path = os.environ["PYTHONPATH"]
        video = pipeline.render(section, {"beats": [{"code": 'self.extension("smoke_visual", 0)'}]}, 0)
        require(video.is_file(), "项目内可信扩展没有真实渲染")
        require(os.environ["PYTHONPATH"] == parent_path and os.environ.get("PYTHONSAFEPATH") == old_safe, "渲染修改了父进程环境")
    finally:
        if old_path is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = old_path
    extension = project / "code/runtime/extensions/visual.py"
    original = extension.read_text(encoding="utf-8")
    extension.write_text(original + "\nCHANGED_INPUT = True\n", encoding="utf-8")
    rejected(lambda: VideoPipeline("数量比较", settings, output, resume=True, project=project), "扩展源码变化后复用了旧缓存")
    extension.write_text(original, encoding="utf-8")
    write_json(project / "code/runtime/extensions.json", {**manifest, "second_visual": manifest["smoke_visual"]})
    rejected(lambda: VideoPipeline("数量比较", settings, output, resume=True, project=project), "注册清单变化后复用了旧缓存")
    return pack
