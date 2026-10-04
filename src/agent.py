import argparse
import importlib.metadata
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from configuration import ROOT, load_config, validate_endpoint


def parser():
    command = argparse.ArgumentParser(description="中文考公教案 → 配音驱动的 Manim 教学视频（Windows）")
    command.add_argument("--config", help="JSON 配置文件，默认 config.local.json")
    command.add_argument("--topic", "--knowledge_point", dest="topic", help="目标知识点")
    command.add_argument("--material", action="append", default=[], help="Markdown/PDF 教材，可重复")
    command.add_argument("--pdf-pages", help="PDF 页码，如 2-5,8；应用于输入的所有 PDF")
    command.add_argument("--output", help="输出目录；默认 outputs/知识点-时间")
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
    command.add_argument("--tts-provider", choices=["edge", "openai", "http", "none"])
    command.add_argument("--tts-voice")
    command.add_argument("--quality", choices=["low", "medium", "high"])
    command.add_argument("--doctor", action="store_true", help="离线检查依赖、FFmpeg、中文字体")
    command.add_argument("--list-models", action="store_true", help="查询所配置服务 /models（服务可能不支持）")
    command.add_argument("--check-api", action="store_true", help="实际调用文本/启用的视觉接口（可能收费）")
    command.add_argument("--check-tts", action="store_true", help="实际合成一句中文测试音频")
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
        raise ValueError(f"中文字体 {font} 未安装，请设置 video.font 为系统已有字体")
    print(f"中文字体: {font}\n基础模式使用 Text，无需 LaTeX、GPU 或 WSL。")


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
    arguments = parser().parse_args(argv)
    overrides = {"text": {}, "vision": {}, "tts": {}, "video": {}}
    for key in ("protocol", "base_url", "api_key", "model"):
        value = getattr(arguments, key)
        if value is not None:
            overrides["text"][key] = value
        value = getattr(arguments, "vision_" + key)
        if value is not None:
            overrides["vision"][key] = value
    for key in ("provider", "voice"):
        if getattr(arguments, "tts_" + key) is not None:
            overrides["tts"][key] = getattr(arguments, "tts_" + key)
    if arguments.feedback is not None:
        overrides["vision"]["enabled"] = arguments.feedback
    if arguments.quality:
        overrides["video"]["quality"] = arguments.quality
    config = None
    try:
        config = load_config(arguments.config, overrides)
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
            info = Narrator(config["tts"]).synthesize("这是一段公务员考试知识点讲解的配音测试。", destination)
            print(f"TTS 验证成功: {destination}\n{json.dumps(info, ensure_ascii=False)}")
            return 0
        if arguments.check_assets:
            from icon_assets import AssetManager
            result = AssetManager(config["assets"], ROOT / "outputs" / "checks").check()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if all(item["ok"] for item in result) else 1
        if not arguments.topic:
            raise ValueError("请提供 --topic 知识点")
        if not arguments.plan_only and arguments.stop_after in ("render", "review", "compose") and not arguments.allow_generated_code:
            raise ValueError("渲染会执行模型生成的 Python。请先 --plan-only 检查教案，确认后使用 --allow-generated-code；建议无敏感文件的隔离账户运行。")
        from pipeline import VideoPipeline
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", arguments.topic).strip(" .")[:60] or "lesson"
        output = arguments.output or ROOT / "outputs" / (safe + "-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        print("注意：教材选段会发送给文本服务；启用评审会上传视频帧，旁白会发送给 TTS 服务。")
        result = VideoPipeline(arguments.topic, config, output, arguments.material, arguments.pdf_pages, arguments.resume, on_event=lambda event: print(f"[{event['stage']}] {event['status']} {event['message']}")).run(arguments.plan_only, arguments.stop_after)
        print(f"完成: {result}")
        return 0
    except Exception as failure:
        message = str(failure)
        if config:
            for role in ("text", "vision", "tts"):
                secret = config[role].get("api_key")
                if secret:
                    message = message.replace(secret, "<redacted>")
        print("失败: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
