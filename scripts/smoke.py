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
            sources = re.findall(r"\[([^\]\n]*lesson\.md:L\d+)\]", prompt)
            result = {"topic": "增长率", "target_audience": "考公考生", "warnings": [], "sections": [{"id": "section_1", "title": "增长率", "goal": "理解分母", "key_points": ["基期作为分母"], "sources": sources[:1]}]}
        elif stage == "STORYBOARD":
            result = {"sections": [{"id": "section_1", "title": "增长率", "beats": [{"narration": "增长率的分母是基期量，不能用现期量。", "caption": "增长率 = 增长量 / 基期量", "visual": "用两个条形图展示100和120"}]}]}
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
    stream.set_data(b"BT /F1 16 Tf 20 240 Td (Base 100, current 120, growth rate 20 percent.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    path = directory / "text.pdf"
    writer.write(str(path))
    extracted = load_materials([path], "growth rate", DEFAULTS["materials"], "1")
    require("100" in extracted["context"] and "#p1" in extracted["context"], "PDF 文本/页码丢失")
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=300)
    scanned = directory / "scan.pdf"
    writer.write(str(scanned))
    try:
        load_materials([scanned], "增长率", DEFAULTS["materials"])
    except ValueError as error:
        require("OCR" in str(error), "扫描PDF错误不明确")
    else:
        raise RuntimeError("空白/扫描 PDF 不应被静默接受")
    require(page_numbers("1-2,4", 4) == [0, 1, 3], "PDF页码筛选失败")


def wait_job(web, identifier):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with web.LOCK:
            job = copy.deepcopy(web.JOBS[identifier])
        if job["status"] in ("complete", "failed"):
            require(job["status"] == "complete", "Web任务失败: " + str(job.get("error") or "未知错误"))
            return job
        time.sleep(0.1)
    raise RuntimeError("Web任务超时")


def check_web(config, directory):
    import web.app as web
    web.WORKSPACE = directory / "web-workspace"
    web.WORKSPACE.mkdir()
    web.JOBS.clear()
    web.current_config = lambda: copy.deepcopy(config)
    web.save_config = lambda updates: merge(config, updates)
    credentials_dir = directory / "credentials-check"
    credentials_dir.mkdir()
    old_credentials = merge(config, {"tts": {"provider": "http", "url": "https://old.example/speech", "headers": {"Authorization": "Bearer old-test-token"}}})
    new_credentials = merge(config, {"tts": {"provider": "http", "url": "https://new.example/speech", "headers": {"Authorization": "Bearer new-test-token"}}})
    (credentials_dir / "settings.json").write_text(json.dumps(public_config(old_credentials)), encoding="utf-8")
    web.current_config = lambda: copy.deepcopy(new_credentials)
    try:
        web.saved_job_config(credentials_dir)
    except ValueError:
        pass
    else:
        raise RuntimeError("HTTP TTS 地址变化后不能恢复 Authorization 到旧地址")
    finally:
        web.current_config = lambda: copy.deepcopy(config)
    client = web.app.test_client()
    headers = {"X-C2V-CSRF": client.get("/api/session").get_json()["csrf"]}
    require(client.get("/").status_code == 200, "Web首页不可用")
    require(client.get("/", headers={"Host": "attacker.example"}).status_code == 403, "Host保护缺失")
    require(client.post("/api/config", json={}).status_code == 403, "CSRF保护缺失")
    exposed = client.get("/api/config").get_data(as_text=True)
    require(config["text"]["api_key"] not in exposed, "配置返回了密钥")
    require(client.post("/api/models", json={}, headers=headers).status_code == 200, "模型列表查询失败")
    response = client.post("/api/jobs", data={"topic": "增长率", "stop_after": "outline", "config": json.dumps(config), "files": (io.BytesIO("# 增长率\n基期100，现期120。".encode()), "lesson.md")}, headers=headers)
    require(response.status_code == 200, response.get_data(as_text=True))
    identifier = response.get_json()["job_id"]
    wait_job(web, identifier)
    snapshot = (web.WORKSPACE / identifier / "settings.json").read_text(encoding="utf-8")
    require(config["text"]["api_key"] not in snapshot, "任务快照复制了真实密钥")
    require(client.get(f"/api/jobs/{identifier}/file/output/outline.json").status_code == 200, "工件不可访问")
    for path in ("output/../settings.json", "output/../job.json", "materials/../settings.json", "output/../../other/settings.json"):
        require(client.get(f"/api/jobs/{identifier}/file/{path}").status_code == 400, "私密路径越权: " + path)
    response = client.post(f"/api/jobs/{identifier}/continue", json={"stop_after": "storyboard", "allow_generated_code": False}, headers=headers)
    require(response.status_code == 200, response.get_data(as_text=True))
    wait_job(web, identifier)
    outline = client.get(f"/api/jobs/{identifier}/file/output/outline.json").get_json()
    outline["sections"][0]["title"] = "修改后的增长率"
    response = client.post(f"/api/jobs/{identifier}/rerun", json={"stop_after": "outline", "edit_name": "outline.json", "edit_data": outline}, headers=headers)
    require(response.status_code == 200, response.get_data(as_text=True))
    changed = response.get_json()["job_id"]
    require(changed != identifier, "修改应创建新版本")
    wait_job(web, changed)
    require(client.get(f"/api/jobs/{changed}/file/output/outline.json").get_json()["sections"][0]["title"] == "修改后的增长率", "编辑丢失")


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
        material.write_text("# 增长率\n基期100，现期120，增长率为20%。", encoding="utf-8")
        output = directory / "pipeline"
        events = []
        pipeline = VideoPipeline("增长率", config, output, [material], on_event=lambda event: events.append(event))
        final = pipeline.run()
        require({"video", "audio", "subtitle"}.issubset({item["type"] for item in probe(final)["streams"]}), "最终视频轨道不完整")
        require(COUNTS.get("CODE", 0) >= 3, "自动调试/视觉反馈没有驱动代码修复")
        counts = dict(COUNTS)
        VideoPipeline("增长率", config, output, [material], resume=True).run()
        require(COUNTS == counts, "续跑不应再次调用模型或TTS")
        switched_config = resolve_config(merge(config, {"vision": {"protocol": "responses"}}))
        VideoPipeline("增长率", switched_config, output, [material], resume=True).run()
        require(COUNTS.get("REVIEW", 0) == counts.get("REVIEW", 0) + 1, "更换视觉模型后必须重新评审")
        require(all(COUNTS.get(stage) == counts.get(stage) for stage in ("OUTLINE", "STORYBOARD", "CODE", "audio")), "更换视觉模型不应重跑前置阶段")
        material.write_text("# 增长率\n修改后的教材内容。", encoding="utf-8")
        try:
            VideoPipeline("增长率", config, output, [material], resume=True)
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
        check_web(config, directory)
        if args.icons:
            from icon_assets import AssetManager
            settings = merge(DEFAULTS["assets"], {"enabled": True, "sources": {name: {"enabled": True} for name in DEFAULTS["assets"]["sources"]}})
            result = AssetManager(settings, directory).check()
            require(len(result) == 3 and all(item["ok"] for item in result), json.dumps(result, ensure_ascii=False))
        print(json.dumps({"ok": True, "output": str(final), "checks": ["Responses", "Chat Completions", "OpenAI TTS", "HTTP TTS", "PDF", "Manim repair", "vision feedback", "FFmpeg MP4", "resume", "narration invalidation", "Web upload/edit/continue", "CSRF", "secret/path protection"], "edge": args.edge, "icons": args.icons}, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
