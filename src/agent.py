import argparse
import contextlib
import importlib.metadata
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from configuration import ROOT, load_config, validate_endpoint


def parser():
    command = argparse.ArgumentParser(description="通用提示词与素材驱动的 CLI 视频流水线")
    command.add_argument("--config", help="JSON 配置文件，默认 config.local.json")
    command.add_argument("--topic", "--knowledge_point", dest="topic", help="目标知识点")
    command.add_argument("--prompt", help="用户视频生成需求；优先于兼容参数 --topic")
    command.add_argument("--style", help="项目画面风格 ID")
    command.add_argument("--reference", action="append", default=[], help="外部参考素材，可重复")
    command.add_argument("--task-file", help="任务 JSON；素材相对路径以该文件所在目录解析")
    command.add_argument("--list-styles", action="store_true")
    command.add_argument("--list-tts", action="store_true")
    command.add_argument("--material", action="append", default=[], help="Markdown/PDF 教材，可重复")
    command.add_argument("--pdf-pages", help="PDF 页码，如 2-5,8；应用于输入的所有 PDF")
    command.add_argument("--output", help="项目目录（兼容旧参数）；新项目产物放在其 output 子目录")
    command.add_argument("--project", help="独立项目目录；默认 video_projects/日期-任务--ID")
    command.add_argument("--project-pack", help="显式注入可信项目包目录（提示词、course/video、教材、扩展）；只用于新项目")
    command.add_argument("--course-file", help="本视频要求 JSON；可含 course/video，或直接 instructions/prompts")
    command.add_argument("--prompts-dir", help="本视频完整提示词模板目录：policy/outline/storyboard/code/review.txt")
    command.add_argument("--resource", "--example", action="append", default=[], help="本视频 SVG、绘图源码或示例文件；可重复，源码仅归档不自动执行")
    command.add_argument("--resume", action="store_true", help="复用同配置任务的教材/大纲/分镜/配音")
    command.add_argument("--plan-only", action="store_true", help="只生成大纲和分镜，不执行模型生成的代码")
    command.add_argument("--stop-after", choices=["outline", "storyboard", "audio", "assets", "code", "render", "review", "compose"], default="compose")
    command.add_argument("--allow-generated-code", action="store_true", help="确认允许执行模型生成的本地 Python（AST 校验不是沙箱）")
    command.add_argument("--protocol", choices=["responses", "chat_completions"])
    command.add_argument("--base-url")
    command.add_argument("--api-key", help="建议用 .env，避免密钥进入 shell 历史")
    command.add_argument("--model", help="任意服务实际支持的模型 ID")
    command.add_argument("--vision-protocol", choices=["responses", "chat_completions"])
    command.add_argument("--vision-base-url")
    command.add_argument("--vision-api-key")
    command.add_argument("--vision-model")
    command.add_argument("--feedback", "--use_feedback", action="store_true", default=None)
    command.add_argument("--no-feedback", "--no_feedback", dest="feedback", action="store_false")
    command.add_argument("--tts-provider", help="edge/openai/http/none 或已注册插件")
    command.add_argument("--tts-voice")
    command.add_argument("--tts-model", help="独立 TTS 模型 ID，不影响文本模型")
    command.add_argument("--tts-base-url", help="独立 TTS 服务地址")
    command.add_argument("--quality", choices=["low", "medium", "high"])
    command.add_argument("--doctor", action="store_true", help="离线检查依赖、FFmpeg、配置字体")
    command.add_argument("--list-models", action="store_true", help="查询所配置服务 /models（服务可能不支持）")
    command.add_argument("--check-api", action="store_true", help="实际调用文本/启用的视觉接口（可能收费）")
    command.add_argument("--check-tts", action="store_true", help="实际合成一句测试音频")
    command.add_argument("--check-assets", action="store_true", help="查询各启用图标源并缓存示例")
    return command


def doctor(config):
    from media import ffmpeg_binary, run_command
    from manimpango import list_fonts
    if sys.version_info < (3, 11):
        raise ValueError("请使用 Python 3.11/3.12，推荐 3.12")
    print(f"Python: {sys.version.split()[0]}\n虚拟环境: {sys.prefix}")
    for package in ("manim", "openai", "edge-tts", "pypdf", "imageio-ffmpeg"):
        print(f"{package}: {importlib.metadata.version(package)}")
    print("FFmpeg: " + run_command([ffmpeg_binary(), "-version"]).splitlines()[0])
    font = config["video"]["font"]
    if font not in list_fonts():
        raise ValueError(f"字体 {font} 未安装，请设置 video.font 为系统已有字体")
    print(f"字体: {font}\n基础模式使用 Text，无需 LaTeX、GPU 或 WSL。")


def validate_runtime(config):
    video = config["video"]
    for key in ("fps", "max_sections", "max_beats", "render_timeout"):
        if not isinstance(video[key], int) or not 1 <= video[key] <= 3600:
            raise ValueError(f"video.{key} 必须是 1-3600 的整数")
    if not isinstance(video["fix_attempts"], int) or not 0 <= video["fix_attempts"] <= 10:
        raise ValueError("video.fix_attempts 必须是 0-10 的整数")
    if video["quality"] not in ("low", "medium", "high"):
        raise ValueError("video.quality 必须是 low/medium/high")
    if not isinstance(video["pause_seconds"], (int, float)) or not 0 <= video["pause_seconds"] <= 5:
        raise ValueError("video.pause_seconds 必须在 0-5 秒内")
    if not isinstance(config["vision"]["frames"], int) or not 1 <= config["vision"]["frames"] <= 20:
        raise ValueError("vision.frames 必须为 1-20 的整数")
    if not isinstance(config["vision"]["rounds"], int) or not 0 <= config["vision"]["rounds"] <= 5:
        raise ValueError("vision.rounds 必须为 0-5 的整数")


def main(argv=None):
    project_guard = contextlib.ExitStack()
    arguments = parser().parse_args(argv)
    overrides = {"text": {}, "vision": {}, "tts": {}, "video": {}}
    for key in ("protocol", "base_url", "api_key", "model"):
        value = getattr(arguments, key)
        if value is not None:
            overrides["text"][key] = value
        value = getattr(arguments, "vision_" + key)
        if value is not None:
            overrides["vision"][key] = value
    for key in ("provider", "voice", "model", "base_url"):
        if getattr(arguments, "tts_" + key) is not None:
            overrides["tts"][key] = getattr(arguments, "tts_" + key)
    if arguments.feedback is not None:
        overrides["vision"]["enabled"] = arguments.feedback
    if arguments.quality:
        overrides["video"]["quality"] = arguments.quality
    config = None
    try:
        if arguments.list_styles:
            from styles import list_styles
            print(json.dumps(list_styles(), ensure_ascii=False, indent=2))
            return 0
        if arguments.list_tts:
            from narration import list_tts_providers
            print(json.dumps(list_tts_providers(), ensure_ascii=False))
            return 0
        from configuration import merge, resolve_config
        config = load_config(arguments.config, overrides, resolved=False)
        if arguments.task_file:
            from task_schema import load_task
            task = load_task(arguments.task_file)
            task_root = Path(arguments.task_file).expanduser().resolve().parent
            config = merge(config, task.get("config", {}))
            config["video_overrides"] = merge(config.get("video_overrides", {}), task.get("config", {}).get("video", {}))
            config = merge(config, {"tts": task.get("tts", {}), "vision": task.get("review", {}), "style": task.get("style", config.get("style", "default"))})
            arguments.prompt = arguments.prompt or task["prompt"]
            for field, target in (("materials", arguments.material), ("references", arguments.reference)):
                for filename in task.get(field, []):
                    path = Path(filename).expanduser()
                    target.append(str(path if path.is_absolute() else task_root / path))
        if arguments.style:
            overrides["style"] = arguments.style
        unresolved_config = merge(config, overrides)
        unresolved_config["video_overrides"] = merge(unresolved_config.get("video_overrides", {}), overrides.get("video", {}))
        config = resolve_config(merge(config, overrides))
        arguments.topic = arguments.prompt or arguments.topic
        if arguments.resume and not arguments.topic and (arguments.project or arguments.output):
            saved_task = Path(arguments.project or arguments.output).expanduser().resolve() / "task.json"
            arguments.topic = json.loads(saved_task.read_text(encoding="utf-8-sig"))["prompt"]
        validate_runtime(config)
        if arguments.doctor:
            doctor(config)
            return 0
        if arguments.list_models:
            from openai import OpenAI
            validate_endpoint(config["text"]["base_url"])
            for model in OpenAI(api_key=config["text"]["api_key"], base_url=config["text"]["base_url"]).models.list():
                print(model.id)
            return 0
        if arguments.check_api:
            from model_gateway import ModelGateway
            gateway = ModelGateway(config["text"])
            print("文本协议连通: " + gateway.request('请只回复 "API OK"', max_tokens=2048)[0])
            if config["vision"]["enabled"]:
                from PIL import Image
                sample = ROOT / "outputs" / "checks" / "vision.png"
                sample.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64, 64), "blue").save(sample)
                response, unused_usage = ModelGateway(config["vision"], "vision").request("说明图片的主要颜色", [sample], 2048)
                print("视觉协议连通: " + response)
            return 0
        if arguments.check_tts:
            from narration import Narrator
            destination = ROOT / "outputs" / "checks" / "tts.wav"
            info = Narrator(config["tts"]).synthesize("这是一段教学视频的配音测试。", destination)
            print(f"TTS 验证成功: {destination}\n{json.dumps(info, ensure_ascii=False)}")
            return 0
        if arguments.check_assets:
            from icon_assets import AssetManager
            result = AssetManager(config["assets"], ROOT / "outputs" / "checks").check()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if all(item["ok"] for item in result) else 1
        if not arguments.topic:
            raise ValueError("请提供 --prompt 视频需求或 --task-file")
        if not arguments.plan_only and arguments.stop_after in ("render", "review", "compose") and not arguments.allow_generated_code:
            raise ValueError("渲染会执行模型生成的 Python。请先 --plan-only 检查教案，确认后使用 --allow-generated-code；建议无敏感文件的隔离账户运行。")
        from pipeline import VideoPipeline
        from configuration import merge, resolve_config
        from video_project import PROMPT_NAMES, apply_project_pack, archive_resource, initialize_project, new_project_path, project_pack_config, restore_project_config, write_json
        if arguments.project and arguments.output:
            raise ValueError("--project 与 --output 不能同时指定")
        if arguments.resume and not (arguments.project or arguments.output):
            raise ValueError("续跑请明确指定 --project 或 --output，避免创建新项目")
        if arguments.resume and any((arguments.project_pack, arguments.course_file, arguments.prompts_dir, arguments.resource, arguments.reference, arguments.task_file)):
            raise ValueError("续跑不能重新注入项目输入，请创建新项目")
        base = Path(arguments.project or arguments.output).expanduser().resolve() if arguments.project or arguments.output else new_project_path(arguments.topic)
        from execution import project_lock
        base.mkdir(parents=True, exist_ok=True)
        project_guard.enter_context(project_lock(base))
        if arguments.resume and (base / "settings.json").is_file():
            config = resolve_config(merge(restore_project_config(base, config), overrides))
        elif (base / "project.json").exists():
            raise ValueError("项目已存在；原配置续跑用 --resume，修改课程请使用新的项目目录")
        elif not arguments.resume:
            config = unresolved_config
        if arguments.project_pack:
            pack_config = project_pack_config(arguments.project_pack)
            config = merge(config, pack_config)
            config["video_overrides"] = merge(config.get("video_overrides", {}), pack_config.get("video", {}))
            config["task"] = merge(config.get("task", {}), pack_config.get("course", {}))
        if arguments.course_file:
            course = json.loads(Path(arguments.course_file).read_text(encoding="utf-8-sig"))
            if not isinstance(course, dict):
                raise ValueError("课程要求必须是 JSON 对象")
            config = merge(config, course if "course" in course or "video" in course else {"course": course})
            config["video_overrides"] = merge(config.get("video_overrides", {}), course.get("video", {}))
            config["task"] = merge(config.get("task", {}), course.get("course", course if "video" not in course else {}))
        config = resolve_config(merge(config, overrides))
        from styles import load_style, style_video_config
        config["video_overrides"] = merge(config.get("video_overrides", {}), overrides.get("video", {}))
        style_id = config.get("style", "default")
        if not arguments.resume:
            config = style_video_config(config, load_style(style_id.get("id") if isinstance(style_id, dict) else style_id))
        if arguments.pdf_pages is not None:
            config.setdefault("course", {})["pdf_pages"] = arguments.pdf_pages
            config.setdefault("task", {})["pdf_pages"] = arguments.pdf_pages
        validate_runtime(config)
        initialize_project(base, arguments.topic, config)
        if arguments.project_pack:
            apply_project_pack(arguments.project_pack, base)
        if not arguments.resume:
            write_json(base / "prompts/requirements.json", config.get("task", config.get("course", {})))
        if arguments.prompts_dir:
            for name in PROMPT_NAMES:
                source = Path(arguments.prompts_dir).expanduser().resolve() / (name + ".txt")
                (base / "prompts" / (name + ".txt")).write_text(source.read_text(encoding="utf-8-sig"), encoding="utf-8")
        for filename in arguments.resource:
            source = Path(filename).expanduser().resolve()
            archive_resource(base, source.name, source.read_bytes(), config["assets"].get("color", "#287D68"))
        output = base if arguments.resume and (base / "manifest.json").is_file() else base / "output"
        print("视频项目目录: " + str(base))
        print("注意：参考文本、图片及视频抽帧会发送给规划模型；启用评审会上传渲染帧，旁白会发送给 TTS，可选转录会上传音频。")
        pages = arguments.pdf_pages or config.get("task", {}).get("pdf_pages") or config.get("course", {}).get("pdf_pages")
        materials = list(arguments.material)
        if not arguments.resume:
            supplied_names = {Path(filename).name.casefold() for filename in materials}
            bundled = [str(file) for file in sorted((base / "input/materials").iterdir()) if file.is_file() and file.name != "index.json"]
            if any(Path(filename).name.casefold() in supplied_names for filename in bundled):
                raise ValueError("输入素材与项目包素材同名，请重命名后重试")
            materials = bundled + materials
        references = list(arguments.reference)
        if not arguments.resume:
            references = [str(file) for file in sorted((base / "input/references").iterdir()) if file.is_file() and file.name != "index.json"] + references
        pipeline = VideoPipeline(arguments.topic, config, output, materials, pages, arguments.resume, on_event=lambda event: print(f"[{event['stage']}] {event['status']} {event['message']}"), project=base, references=references)
        if not arguments.resume:
            from configuration import public_config
            write_json(base / "task.json", {"schema_version": 1, "prompt": arguments.topic, "style": pipeline.style.id, "materials": ["input/materials/" + name for name in json.loads((base / "input/materials/index.json").read_text(encoding="utf-8"))["files"]], "references": ["input/references/" + name for name in json.loads((base / "input/references/index.json").read_text(encoding="utf-8"))["files"]], "config": {}, "tts": {}, "review": {}})
        result = pipeline.run(arguments.plan_only, arguments.stop_after)
        print(f"完成: {result}")
        return 0
    except Exception as failure:
        from configuration import sanitize_error
        message = sanitize_error(str(failure), config)
        if config:
            for role in ("text", "vision", "tts"):
                secret = config[role].get("api_key")
                if secret:
                    message = message.replace(secret, "<redacted>")
        print("失败: " + message, file=sys.stderr)
        return 1
    finally:
        project_guard.close()


if __name__ == "__main__":
    raise SystemExit(main())
