import json
import os
import secrets
import re
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory, abort
from waitress import serve

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from configuration import load_config, merge, public_config, resolve_config, sanitize_error
from pipeline import VideoPipeline

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.RLock()
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="code2video")
CSRF_TOKEN = secrets.token_urlsafe(32)


@app.before_request
def local_only():
    host = request.host.split(":")[0]
    if host not in ("127.0.0.1", "localhost"):
        abort(403)
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        abort(403)
    if request.method in ("POST", "PUT", "DELETE") and not secrets.compare_digest(request.headers.get("X-C2V-CSRF", ""), CSRF_TOKEN):
        abort(403)


@app.after_request
def secure_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; frame-ancestors 'none'"
    return response


@app.get("/api/session")
def session_token():
    return jsonify({"csrf": CSRF_TOKEN})


def redact(config):
    view = public_config(config)
    effective = resolve_config(config)
    for role in ("text", "vision", "tts"):
        view.setdefault(role, {})["api_key_configured"] = bool(effective.get(role, {}).get("api_key"))
        view[role]["api_key"] = ""
    return view


def current_config():
    return load_config(resolved=False)


def restore_credentials(snapshot, current):
    if not isinstance(snapshot, dict):
        return snapshot
    current = current if isinstance(current, dict) else {}
    return {
        key: current.get(key) if value == "<redacted>" else restore_credentials(value, current.get(key, {}) if isinstance(current, dict) else {})
        for key, value in snapshot.items()
    }


def needs_credentials(value):
    if isinstance(value, dict):
        return any(needs_credentials(item) for item in value.values())
    if isinstance(value, list):
        return any(needs_credentials(item) for item in value)
    return value == "<redacted>"


def saved_job_config(base):
    snapshot = json.loads((base / "settings.json").read_text(encoding="utf-8"))
    current = current_config()
    previous_effective = resolve_config(snapshot)
    current_effective = resolve_config(current)
    for role in ("text", "vision", "tts"):
        settings = previous_effective.get(role, {})
        if needs_credentials(settings) and any(settings.get(key) != current_effective.get(role, {}).get(key) for key in ("base_url", "url")):
            raise ValueError("任务服务地址与当前凭证配置不一致；请恢复原服务地址或创建新版本")
    return restore_credentials(snapshot, current)


def save_config(updates):
    if not isinstance(updates, dict):
        raise ValueError("配置必须是 JSON 对象")
    updates = json.loads(json.dumps(updates))
    for role in ("text", "vision", "tts"):
        updates.get(role, {}).pop("api_key_configured", None)
    config = merge(current_config(), updates)
    target = ROOT / "config.local.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return config


def sanitized(message, config=None):
    return sanitize_error(message, config or current_config())


def persist(job_id):
    target = job_root(job_id) / "job.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(JOBS[job_id], ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def job_root(job_id):
    base = (WORKSPACE / job_id).resolve()
    if base.parent != WORKSPACE.resolve():
        raise ValueError("非法任务 ID")
    return base


def safe_file(job_id, relative):
    base = job_root(job_id)
    target = (base / relative).resolve()
    allowed = [base / "output", base / "materials"]
    if not any(root in target.parents for root in allowed):
        raise ValueError("该路径不是公开产物")
    return base, target


def emit(job_id, event):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["events"].append({"time": datetime.now().isoformat(timespec="seconds"), **event})
        job["stage"] = event.get("stage", job["stage"])
        job["stage_status"] = event.get("status", job["stage_status"])
        job["message"] = event.get("message", "")
        persist(job_id)


def run_job(job_id, topic, uploads, config, stop_after, allow_generated_code, resume=False, seeds=None):
    base = job_root(job_id)
    material_paths = []
    try:
        with LOCK:
            JOBS[job_id].update({"status": "running", "started_at": datetime.now().isoformat(timespec="seconds")})
        material_dir = base / "materials"
        material_dir.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            target = material_dir / upload["name"]
            target.write_bytes(upload["data"])
            material_paths.append(str(target))
        if resume:
            material_paths = [str(file) for file in material_dir.iterdir() if file.suffix.lower() in (".pdf", ".md", ".markdown")]
        output = base / "output"
        output.mkdir(parents=True, exist_ok=True)
        for name, data in (seeds or {}).items():
            (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if stop_after in ("render", "review", "compose") and not allow_generated_code:
            raise ValueError("渲染阶段需要确认执行模型生成的本地代码")
        from agent import validate_runtime
        effective = resolve_config(config)
        validate_runtime(effective)
        pipeline = VideoPipeline(topic, effective, output, material_paths, config.get("course", {}).get("pdf_pages"), resume=resume, on_event=lambda event: emit(job_id, {**event, "message": sanitized(event.get("message", ""), config)}))
        result = pipeline.run(stop_after=stop_after)
        with LOCK:
            JOBS[job_id].update({"status": "complete", "result": str(result), "finished_at": datetime.now().isoformat(timespec="seconds")})
            persist(job_id)
    except Exception as error:
        with LOCK:
            JOBS[job_id].update({"status": "failed", "error": sanitized(error, config), "finished_at": datetime.now().isoformat(timespec="seconds")})
            persist(job_id)
        emit(job_id, {"stage": JOBS.get(job_id, {}).get("stage", "unknown"), "status": "failed", "message": sanitized(error, config)[:1000]})


def make_job(topic, files, config, stop_after, allow_generated_code, parent=None, seeds=None):
    if stop_after not in ("outline", "storyboard", "audio", "assets", "code", "render", "review", "compose"):
        raise ValueError("无效阶段")
    job_id = uuid.uuid4().hex[:12]
    base = job_root(job_id)
    base.mkdir(parents=True, exist_ok=False)
    uploads = []
    for file in files:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(file.filename or "material").name)
        name = name.strip(" .")
        if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
            name = "material_" + name
        if any(upload["name"] == name for upload in uploads):
            raise ValueError("上传教材存在重复文件名，请重命名")
        if Path(name).suffix.lower() not in (".md", ".markdown", ".pdf"):
            raise ValueError("教材仅支持 Markdown/PDF")
        data = file.read()
        if not data or len(data) > 50 * 1024 * 1024:
            raise ValueError(f"教材为空或超过 50MB: {name}")
        uploads.append({"name": name, "data": data})
    with LOCK:
        JOBS[job_id] = {
            "id": job_id, "topic": topic, "status": "queued", "stage": "queued", "stage_status": "waiting",
            "message": "等待运行", "events": [], "result": None, "parent": parent,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        persist(job_id)
    (base / "settings.json").write_text(json.dumps(public_config(config), ensure_ascii=False), encoding="utf-8")
    EXECUTOR.submit(run_job, job_id, topic, uploads, config, stop_after, allow_generated_code, seeds=seeds)
    return job_id


@app.get("/")
def index():
    return send_from_directory(ROOT / "web", "index.html")


@app.get("/app.js")
def javascript():
    return send_from_directory(ROOT / "web", "app.js")


@app.post("/api/models")
def models():
    try:
        from openai import OpenAI
        config = resolve_config(merge(current_config(), request.get_json(force=True) or {}))
        text = config["text"]
        identifiers = [model.id for model in OpenAI(api_key=text["api_key"], base_url=text["base_url"], timeout=30, max_retries=0).models.list()]
        return jsonify({"models": identifiers})
    except Exception as error:
        return jsonify({"error": sanitized(error)}), 400


@app.post("/api/tts/test")
def tts_test():
    try:
        from narration import Narrator
        config = resolve_config(merge(current_config(), request.get_json(force=True) or {}))
        destination = WORKSPACE / "tts-check.wav"
        result = Narrator(config["tts"]).synthesize("增长率的分母是基期量，不是现期量。", destination)
        return jsonify({"ok": True, "audio_url": "/api/tts/audio", "result": result})
    except Exception as error:
        return jsonify({"error": sanitized(error)}), 400


@app.get("/api/tts/audio")
def tts_audio():
    return send_file(WORKSPACE / "tts-check.wav")


@app.post("/api/jobs/<job_id>/continue")
def continue_job(job_id):
    try:
        base = job_root(job_id)
        payload = request.get_json(force=True) or {}
        with LOCK:
            previous = JOBS[job_id]
            if previous["status"] in ("running", "queued"):
                raise ValueError("任务正在运行")
            stop_after = payload.get("stop_after", "compose")
            if stop_after not in ("outline", "storyboard", "audio", "assets", "code", "render", "review", "compose"):
                raise ValueError("无效阶段")
            config = saved_job_config(base)
            previous.update({"status": "queued", "error": None, "message": "等待续跑"})
            persist(job_id)
        EXECUTOR.submit(run_job, job_id, previous["topic"], [], config, stop_after, bool(payload.get("allow_generated_code")), True)
        return jsonify({"ok": True, "job_id": job_id})
    except Exception as error:
        return jsonify({"error": sanitized(error)}), 400


def restore_jobs():
    for target in WORKSPACE.glob("*/job.json"):
        try:
            job = json.loads(target.read_text(encoding="utf-8"))
            if job["status"] in ("running", "queued"):
                job.update({"status": "interrupted", "message": "服务已重启，可继续运行"})
            JOBS[job["id"]] = job
        except (ValueError, KeyError):
            continue


restore_jobs()


@app.get("/api/config")
def get_config():
    return jsonify(redact(current_config()))


@app.post("/api/config")
def update_config():
    try:
        payload = request.get_json(force=True)
        if not isinstance(payload, dict):
            raise ValueError("JSON 配置必须是对象")
        saved = save_config(payload)
        return jsonify({"ok": True, "config": redact(saved)})
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/config/test")
def test_config():
    try:
        payload = request.get_json(force=True) or {}
        config = resolve_config(merge(current_config(), payload))
        from agent import doctor
        doctor(config)
        checks = {"local": True}
        if config["text"].get("api_key") and config["text"].get("model"):
            from model_gateway import ModelGateway
            checks["text"] = ModelGateway(config["text"]).request('只回复 "API OK"', max_tokens=2048)[0]
        checks["tts"] = config["tts"].get("provider", "edge")
        return jsonify({"ok": True, "checks": checks})
    except Exception as error:
        return jsonify({"ok": False, "error": sanitized(error)}), 400


@app.get("/api/jobs")
def jobs():
    with LOCK:
        return jsonify(list(JOBS.values()))


@app.get("/api/jobs/<job_id>")
def get_job(job_id):
    with LOCK:
        value = JOBS.get(job_id)
        if not value:
            return jsonify({"error": "任务不存在；重启后历史结果仍保存在 workspace"}), 404
        return jsonify(value)


@app.post("/api/jobs")
def start_job():
    try:
        topic = (request.form.get("topic") or "").strip()
        if not topic or len(topic) > 200:
            raise ValueError("请输入 1-200 字的知识点")
        config_payload = json.loads(request.form.get("config") or "{}")
        config = save_config(config_payload) if request.form.get("save_config") == "true" else merge(current_config(), config_payload)
        config.setdefault("course", {})["pdf_pages"] = request.form.get("pdf_pages") or None
        stop_after = request.form.get("stop_after", "compose")
        if stop_after not in ("outline", "storyboard", "audio", "assets", "code", "render", "review", "compose"):
            raise ValueError("无效流水线阶段")
        job_id = make_job(topic, request.files.getlist("materials"), config, stop_after, request.form.get("allow_generated_code") == "true")
        return jsonify({"ok": True, "job_id": job_id})
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/jobs/<job_id>/rerun")
def rerun_job(job_id):
    try:
        base = job_root(job_id)
        material_dir = base / "materials"
        if not material_dir.is_dir():
            raise ValueError("原任务没有可复用教材")
        with LOCK:
            previous = JOBS.get(job_id)
        if not previous:
            raise ValueError("任务仅存在于磁盘，无法从 Web 读取主题；请重新创建任务")
        payload = request.get_json(force=True) or {}
        config = save_config(payload.get("config", {})) if payload.get("save_config") else merge(current_config(), payload.get("config", {}))
        files = []
        for item in material_dir.iterdir():
            if item.suffix.lower() in (".md", ".markdown", ".pdf"):
                files.append(type("Upload", (), {"filename": item.name, "read": lambda self, path=item: path.read_bytes()})())
        seeds = {}
        edit_name = payload.get("edit_name")
        if edit_name:
            if edit_name not in ("outline.json", "storyboard.json") and not re.fullmatch(r"section_\d+_code\.json", edit_name):
                raise ValueError("只能编辑大纲、分镜和 Manim 代码工件")
            edited = payload["edit_data"]
            if edit_name != "outline.json":
                seeds["outline.json"] = json.loads((base / "output/outline.json").read_text(encoding="utf-8"))
            if edit_name not in ("outline.json", "storyboard.json"):
                seeds["storyboard.json"] = json.loads((base / "output/storyboard.json").read_text(encoding="utf-8"))
            seeds[edit_name] = edited
        new_id = make_job(payload.get("topic", previous["topic"]), files, config, payload.get("stop_after", "compose"), bool(payload.get("allow_generated_code")), parent=job_id, seeds=seeds)
        return jsonify({"ok": True, "job_id": new_id})
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.get("/api/jobs/<job_id>/file/<path:relative>")
def artifact(job_id, relative):
    try:
        if not relative.startswith(("output/", "materials/")) or Path(relative).suffix.lower() not in (".json", ".md", ".pdf", ".srt", ".py", ".txt", ".log", ".jpg", ".png", ".svg", ".mp4", ".wav"):
            raise ValueError("该文件不是公开产物")
        base, target = safe_file(job_id, relative)
        if not target.is_file():
            return jsonify({"error": "文件不存在"}), 404
        return send_file(target)
    except Exception as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/asset-check")
def asset_check():
    try:
        from icon_assets import AssetManager
        result = AssetManager(resolve_config(current_config())["assets"], WORKSPACE / "asset-check").check()
        return jsonify({"ok": all(item["ok"] for item in result), "sources": result})
    except Exception as error:
        return jsonify({"ok": False, "error": str(error)}), 400


def main():
    host = os.getenv("C2V_WEB_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("本面板仅支持本机监听；不能无认证暴露到公网")
    port = int(os.getenv("C2V_WEB_PORT", "8787"))
    print(f"Code2Video Web: http://{host}:{port}")
    serve(app, host=host, port=port, threads=4)


if __name__ == "__main__":
    main()
