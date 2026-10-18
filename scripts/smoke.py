import argparse
import base64
import copy
import io
import json
import math
import re
import sys
import threading
import time
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from configuration import DEFAULTS, merge, public_config, resolve_config, sanitize_error
from materials import load_materials, page_numbers
from media import probe
from model_gateway import ModelGateway
from narration import Narrator
from pipeline import VideoPipeline


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sample_audio():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        samples = [int(2000 * math.sin(index * 2 * math.pi * 220 / 24000)) for index in range(24000)]
        audio.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))
    return buffer.getvalue()


COUNTS = {}
AUDIO = sample_audio()


class MockService(BaseHTTPRequestHandler):
    def log_message(self, *arguments):
        pass

    def send(self, data, mime="application/json"):
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8") if mime == "application/json" else data
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.send({"object": "list", "data": [{"id": "smoke-model", "object": "model", "created": 0, "owned_by": "local"}]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/speech") or self.path == "/http-speech":
            COUNTS["audio"] = COUNTS.get("audio", 0) + 1
            self.send(AUDIO, "audio/wav")
            return
        if self.path == "/http-base64":
            self.send({"data": {"audio": base64.b64encode(AUDIO).decode()}})
            return
        messages = payload.get("input") or payload.get("messages")
        content = messages[0]["content"]
        prompt = content[0]["text"]
        match = re.search(r"阶段: (OUTLINE|STORYBOARD|CODE|REVIEW)", prompt)
        stage = match[1] if match else "PROBE"
        COUNTS[stage] = COUNTS.get(stage, 0) + 1
        if stage == "OUTLINE":
            sources = re.findall(r"\[([^\]\n]+(?:\:L\d+|#p\d+))\]", prompt)
            result = {"topic": "数量比较", "target_audience": "学习者", "warnings": [], "sections": [{"id": "section_1", "title": "数量比较", "goal": "比较大小", "key_points": ["数量120大于100"], "sources": sources[:1]}]}
        elif stage == "STORYBOARD":
            result = {"sections": [{"id": "section_1", "title": "数量比较", "beats": [{"narration": "两组数量分别是一百和一百二十，第二组更多。", "caption": "120 > 100", "visual": "用两个条形图展示100和120"}]}]}
        elif stage == "CODE":
            code = "self.add(undefined_object)" if COUNTS[stage] == 1 else "base_bar = Rectangle(width=2, height=2, color=BLUE).shift(LEFT * 2)\ncurrent_bar = Rectangle(width=2, height=2.4, color=GREEN).shift(RIGHT * 2)\nself.play(Create(base_bar), Create(current_bar), run_time=0.5)"
            result = {"beats": [{"code": code}]}
        elif stage == "REVIEW":
            require(len(content) > 1, "视觉请求缺少图像")
            result = {"has_issues": COUNTS[stage] == 1, "suggested_improvements": ["增加两根柱子的颜色对比"] if COUNTS[stage] == 1 else []}
        else:
            result = {"ok": True}
        text = json.dumps(result, ensure_ascii=False)
        if self.path.endswith("responses"):
            self.send({"id": "resp_mock", "object": "response", "created_at": int(time.time()), "status": "completed", "output": [{"id": "msg_mock", "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}], "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20}})
        else:
            self.send({"id": "chat_mock", "object": "chat.completion", "created": int(time.time()), "model": "smoke-model", "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})


def check_pdf(directory):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 16 Tf 20 240 Td (Group A 100, group B 120, difference 20.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    path = directory / "text.pdf"
    writer.write(str(path))
    extracted = load_materials([path], "quantity comparison", DEFAULTS["materials"], "1")
    require("100" in extracted["context"] and "#p1" in extracted["context"], "PDF 文本/页码丢失")
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=300)
    scanned = directory / "scan.pdf"
    writer.write(str(scanned))
    scanned_input = load_materials([scanned], "数量比较", DEFAULTS["materials"])
    require(not scanned_input["selected_chunks"] and "note" in scanned_input["sources"][0], "未解析 PDF 必须明确标注")
    require(page_numbers("1-2,4", 4) == [0, 1, 3], "PDF页码筛选失败")




def check_project_cli(config, directory, pack):
    import contextlib
    from agent import main as run_cli
    from lesson_prompts import TEMPLATES
    from video_project import safe_name
    fixture = directory / "cli-config.json"
    fixture.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    requirements = directory / "course-input.json"
    requirements.write_text(json.dumps({"course": {"instructions": "CLI_COURSE_ONLY", "prompts": {"outline": "CLI_OUTLINE_ONLY"}}, "video": {"theme": "light"}}, ensure_ascii=False), encoding="utf-8")
    templates = directory / "cli-template-inputs"
    templates.mkdir()
    for name, template in TEMPLATES.items():
        (templates / (name + ".txt")).write_text(template + "\nCLI_TEMPLATE_ONLY", encoding="utf-8")
    material = directory / "cli-lesson.md"
    material.write_text("# 数量比较\n两组数量分别为100和120，第二组比第一组多20。", encoding="utf-8")
    drawing = directory / "draw_svg.py"
    drawing.write_text("def draw_svg():\n    return 'local drawing'\n", encoding="utf-8")
    base = directory / "cli-video-project"
    common = ["--config", str(fixture), "--project", str(base), "--topic", "数量比较", "--protocol", "responses", "--base-url", config["text"]["base_url"], "--api-key", config["text"]["api_key"], "--model", "smoke-model", "--no-feedback", "--tts-provider", "http"]
    require(run_cli(common + ["--project-pack", str(pack), "--course-file", str(requirements), "--prompts-dir", str(templates), "--material", str(material), "--resource", str(drawing), "--plan-only"]) == 0, "CLI 独立项目创建失败")
    require((base / "output/storyboard.json").is_file(), "CLI 输出目录不正确")
    require((base / "code/svg/draw_svg.py").is_file(), "CLI 绘图源码未归档")
    requests = "\n".join(file.read_text(encoding="utf-8") for file in (base / "output/requests").glob("*.txt"))
    require(all(marker in requests for marker in ("CLI_COURSE_ONLY", "CLI_OUTLINE_ONLY", "CLI_TEMPLATE_ONLY", "PACK_MATERIAL_ONLY")), "本视频专属提示词未用于 CLI 请求")
    material.unlink()
    counts = dict(COUNTS)
    require(run_cli(common + ["--resume", "--stop-after", "storyboard"]) == 0, "CLI 删除外部原件后不能从项目教材副本续跑")
    require(COUNTS == counts, "CLI 项目续跑不应重新调用模型")
    template = base / "prompts/outline.txt"
    template.write_text(template.read_text(encoding="utf-8") + "\nCHANGED_PROJECT_INPUT", encoding="utf-8")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        result = run_cli(common + ["--resume", "--stop-after", "storyboard"])
    require(result == 1 and "提示词" in captured.getvalue(), "修改完整模板后复用了过期缓存")
    require(safe_name("a" * 100 + ".pdf").endswith(".pdf"), "长文件名丢失教材扩展名")
    require(safe_name("COM9.py") != "COM9.py", "Windows 保留文件名未处理")


def main():
    parser = argparse.ArgumentParser(description="本地协议模拟 + 真实Manim/FFmpeg验收；不消耗外部模型费用")
    parser.add_argument("--edge", action="store_true", help="同时使用真实联网Edge配音")
    parser.add_argument("--icons", action="store_true", help="同时检查三个真实联网图标源")
    args = parser.parse_args()
    directory = ROOT / "outputs" / ("smoke-" + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockService)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    config = resolve_config(merge(DEFAULTS, {"text": {"api_key": "sk-smoke-secret-0123456789", "base_url": base + "/v1", "model": "smoke-model", "protocol": "responses", "max_retries": 0}, "vision": {"enabled": True, "protocol": "chat_completions", "rounds": 1, "frames": 2}, "tts": {"provider": "edge" if args.edge else "http", "url": base + "/http-speech", "payload": {"text": "{text}"}}, "video": {"quality": "low", "fps": 15, "max_sections": 1, "max_beats": 1}, "assets": {"enabled": False}}))
    try:
        for protocol in ("responses", "chat_completions"):
            settings = {**config["text"], "protocol": protocol}
            require(ModelGateway(settings).json("protocol probe")["ok"], protocol + "协议失败")
        for provider in ("openai", "http"):
            settings = {"provider": provider, "base_url": base + "/v1", "api_key": "mock", "model": "speech-model", "voice": "mock", "url": base + "/http-base64", "payload": {"text": "{text}"}, "audio_base64_field": "data.audio"}
            info = Narrator(settings).synthesize("配音接口测试", directory / f"{provider}.wav")
            require(info["duration"] >= 0.99, provider + "TTS失败")
        check_pdf(directory)
        secret = config["text"]["api_key"]
        require(secret not in json.dumps(public_config({"token": secret, "text": config["text"]})), "密钥未脱敏")
        require(secret not in sanitize_error("Authorization: Bearer " + secret, config), "错误未脱敏")
        material = directory / "lesson.md"
        material.write_text("# 数量比较\n两组数量分别为100和120，第二组比第一组多20。", encoding="utf-8")
        output = directory / "pipeline"
        events = []
        pipeline = VideoPipeline("数量比较", config, output, [material], on_event=lambda event: events.append(event))
        final = pipeline.run()
        require({"video", "audio", "subtitle"}.issubset({item["type"] for item in probe(final)["streams"]}), "最终视频轨道不完整")
        require(COUNTS.get("CODE", 0) >= 3, "自动调试/视觉反馈没有驱动代码修复")
        counts = dict(COUNTS)
        VideoPipeline("数量比较", config, output, [material], resume=True).run()
        require(COUNTS == counts, "续跑不应再次调用模型或TTS")
        require((output / "input/materials/lesson.md").is_file(), "CLI 素材原件未复制到项目")
        require((output / "code/manim/section_1_revision_0.py").is_file(), "Manim 绘图源码未存入项目")
        require(config["text"]["api_key"] not in (output / "settings.json").read_text(encoding="utf-8"), "项目快照保存了真实密钥")
        switched_config = resolve_config(merge(config, {"vision": {"protocol": "responses"}}))
        VideoPipeline("数量比较", switched_config, output, [material], resume=True).run()
        require(COUNTS.get("REVIEW", 0) == counts.get("REVIEW", 0) + 1, "更换视觉模型后必须重新评审")
        require(all(COUNTS.get(stage) == counts.get(stage) for stage in ("OUTLINE", "STORYBOARD", "CODE", "audio")), "更换视觉模型不应重跑前置阶段")
        material.write_text("# 数量比较\n修改后的教材内容。", encoding="utf-8")
        try:
            VideoPipeline("数量比较", config, output, [material], resume=True)
        except ValueError:
            pass
        else:
            raise RuntimeError("更换视觉模型不能绕过教材变化校验")
        section = {"id": "section_cache", "beats": [{"narration": "原旁白"}]}
        pipeline.prepare_audio(section)
        before = json.loads((output / "audio/section_cache_01.json").read_text(encoding="utf-8"))["fingerprint"]
        section["beats"][0]["narration"] = "已经修改的新旁白"
        pipeline.prepare_audio(section)
        after = json.loads((output / "audio/section_cache_01.json").read_text(encoding="utf-8"))["fingerprint"]
        require(before != after, "修改旁白后复用了过期配音")
        from project_smoke import check_projects
        pack = check_projects(config, directory)
        check_project_cli(config, directory, pack)
        if args.icons:
            from icon_assets import AssetManager
            settings = merge(DEFAULTS["assets"], {"enabled": True, "sources": {name: {"enabled": True} for name in DEFAULTS["assets"]["sources"]}})
            result = AssetManager(settings, directory).check()
            require(len(result) == 3 and all(item["ok"] for item in result), json.dumps(result, ensure_ascii=False))
        print(json.dumps({"ok": True, "output": str(final), "checks": ["Responses", "Chat Completions", "OpenAI TTS", "HTTP TTS", "PDF", "Manim repair", "vision feedback", "FFmpeg MP4", "resume", "narration invalidation", "independent video projects", "full prompt editing", "SVG/source archiving", "project restore", "secret/path protection", "project packs", "extension manifest/AST", "runtime code invalidation", "isolated PYTHONPATH", "real extension render"], "edge": args.edge, "icons": args.icons}, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
