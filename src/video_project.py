import copy
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from configuration import ROOT, public_config, resolve_config
from lesson_prompts import TEMPLATES
from project_extensions import read_extensions


VIDEO_PROJECTS = ROOT / "video_projects"
PROJECTS = VIDEO_PROJECTS
PROMPT_NAMES = tuple(TEMPLATES)
RESOURCE_SUFFIXES = {".svg", ".py", ".md", ".markdown", ".json", ".txt", ".png", ".jpg"}


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .") or "lesson"
    suffix = Path(name).suffix
    name = name[:70 - len(suffix)] + suffix if 0 < len(suffix) <= 10 and len(name) > 70 else name[:70]
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", name.split(".")[0], re.I):
        name = "lesson_" + name
    return name


def new_project_path(topic, directory=PROJECTS, identifier=None):
    identifier = identifier or uuid.uuid4().hex[:12]
    if not re.fullmatch(r"[a-f0-9]{12}", identifier):
        raise ValueError("非法项目 ID")
    return Path(directory).resolve() / (datetime.now().strftime("%Y%m%d") + "-" + safe_name(topic) + "--" + identifier)


def write_json(filename, value):
    filename = Path(filename)
    boundary = filename.parent.resolve()
    contained(boundary, filename)
    contained(boundary, filename.with_suffix(filename.suffix + ".tmp"))
    filename.parent.mkdir(parents=True, exist_ok=True)
    temporary = filename.with_suffix(filename.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(filename)


def contained(base, target):
    base, target = Path(base).resolve(), Path(target).resolve()
    if base not in target.parents:
        raise ValueError("项目文件路径越界")
    return target


def project_pack_config(source):
    source = Path(source).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("项目包目录不存在")
    target = contained(source, source / "course.json")
    if not target.is_file():
        return {}
    config = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or set(config) - {"course", "video"}:
        raise ValueError("项目包 course.json 只能声明 course/video，不能包含服务或凭证配置")
    if any(not isinstance(value, dict) for value in config.values()):
        raise ValueError("项目包 course/video 必须是 JSON 对象")
    return config


def apply_project_pack(source, destination):
    source, destination = Path(source).expanduser().resolve(), Path(destination).resolve()
    project_pack_config(source)
    mapping = {"prompts": "prompts", "materials": "input/materials", "examples": "input/references", "input/materials": "input/materials", "input/references": "input/references", "code/runtime/extensions": "code/runtime/extensions"}
    for directory, destination_directory in mapping.items():
        for file in sorted((source / directory).rglob("*")):
            if not file.is_file() or "__pycache__" in file.parts:
                continue
            contained(source, file)
            if directory == "prompts" and (file.parent != source / "prompts" or file.name not in {name + ".txt" for name in PROMPT_NAMES}):
                continue
            target = contained(destination, destination / destination_directory / file.relative_to(source / directory))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
    manifest = contained(source, source / "code/runtime/extensions.json")
    if manifest.is_file():
        shutil.copy2(manifest, contained(destination, destination / "code/runtime/extensions.json"))
    read_templates(destination)
    read_extensions(destination / "code/runtime")


def initialize_project(base, topic, config, identifier=None, parent=None):
    base = Path(base).resolve()
    base.mkdir(parents=True, exist_ok=True)
    for relative in ("project.json", "task.json", "settings.json", "prompts/requirements.json", "code/runtime/extensions.json"):
        target = base / relative
        contained(base, target)
        contained(base, target.with_suffix(target.suffix + ".tmp"))
    for name in ("input/materials", "input/references", "input/assets", "prompts", "code/runtime", "code/svg", "generated", "assets", "audio", "render", "review", "requests", "logs", "output"):
        contained(base, base / name).mkdir(parents=True, exist_ok=True)
    metadata = base / "project.json"
    if not metadata.exists():
        identity = re.search(r"--([a-f0-9]{12})$", base.name)
        write_json(metadata, {"schema_version": 2, "id": identifier or (identity[1] if identity else uuid.uuid4().hex[:12]), "prompt": topic, "parent": parent, "created_at": datetime.now().isoformat(timespec="seconds"), "layout": {"input": "input", "prompts": "prompts", "code": "code", "generated": "generated", "render": "render", "review": "review", "output": "output"}})
    for name, template in TEMPLATES.items():
        target = contained(base, base / "prompts" / (name + ".txt"))
        if not target.exists():
            target.write_text(template, encoding="utf-8")
    requirements = base / "prompts/requirements.json"
    if not requirements.exists():
        write_json(requirements, config.get("task", config.get("course", {})))
    task_file = base / "task.json"
    if not task_file.exists():
        style = config.get("style", "default")
        style = style.get("id", "default") if isinstance(style, dict) else style
        write_json(task_file, {"schema_version": 1, "prompt": topic, "style": style, "materials": [], "references": [], "config": {}, "tts": {}, "review": {}})
    style_id = config.get("style", "default")
    style_id = style_id.get("id", "default") if isinstance(style_id, dict) else style_id
    studio_style = style_id in {"studio_noir", "studio_editorial", "studio_sketch"}
    task = config.get("task", config.get("course", {}))
    cube_baseline = studio_style and task.get("component_profile") == "cube_baseline"
    runtime_files = ("scene_runtime.py", "project_extensions.py") + (("series_style.py", "handdrawn_runtime.py", "handdrawn_bridge.cjs") if studio_style else ()) + (("cube_geometry.py", "studio_components.py", "rough_square.json") if cube_baseline else ())
    for name in runtime_files:
        target = contained(base, base / "code/runtime" / name)
        if not target.exists():
            shutil.copy2(ROOT / "src" / name, target)
    if studio_style:
        vendor_source = ROOT / "src/vendor/handdrawn"
        vendor_target = contained(base, base / "code/runtime/vendor/handdrawn")
        if not vendor_target.exists():
            shutil.copytree(vendor_source, vendor_target)
    if not (base / "code/runtime/extensions.json").exists():
        entries = {
            "cube_lesson": {"file": "extensions/studio_entry.py", "entrypoint": "cube_lesson", "description": "Exact cube-net lesson: self.extension('cube_lesson', stage=N), N=0 hook,1 all 11 nets in four families,2 question E/D,3 fold exact hinges,4 re-unfold D with 180 degree material rotation,5 answer A (E original top = D original top). Call once per beat, six beats in order. Do not add duplicate labels."},
            "studio": {"file": "extensions/studio_entry.py", "entrypoint": "studio", "description": "Reusable Manim layout: self.extension('studio', kind='comparison'|'steps', items=['short text',...]). Comparison exactly2 items, steps 1..4."}
        } if cube_baseline else {}
        write_json(base / "code/runtime/extensions.json", entries)
        if cube_baseline:
            entry = base / "code/runtime/extensions/studio_entry.py"
            entry.parent.mkdir(exist_ok=True)
            entry.write_text("from studio_components import cube_lesson, studio\n", encoding="utf-8")
    read_extensions(base / "code/runtime")
    if not (base / "settings.json").exists():
        write_json(base / "settings.json", public_config(config))
    documentation = {
        "README.md": f"# 视频项目：{topic}\n\n每个任务拥有独立目录。task.json 保存任务输入，settings.json 保存脱敏配置。input/materials 与 input/references 保存原始素材；prompts 保存完整提示词与风格快照；code/runtime 保存可信运行时代码；output 保存大纲、分镜、音频、渲染、请求记录和最终视频。\n\n输入或风格改变时创建新项目，不复用旧缓存。上传源码仅归档，不自动执行。请勿公开含私有素材的项目目录。\n",
    }
    for relative, text in documentation.items():
        target = contained(base, base / relative)
        if not target.exists():
            target.write_text(text, encoding="utf-8")
    return base


def read_templates(base):
    result = {}
    for name in PROMPT_NAMES:
        target = contained(base, Path(base) / "prompts" / (name + ".txt"))
        text = target.read_text(encoding="utf-8-sig")
        if not text.strip() or len(text) > 200000:
            raise ValueError("提示词模板为空或过大: " + name)
        result[name] = text
    return result


def input_fingerprint(base):
    digest = hashlib.sha256()
    for directory in ("prompts", "input", "code/runtime", "code/svg", "assets"):
        for file in sorted((Path(base) / directory).rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                contained(base, file)
                digest.update(file.relative_to(base).as_posix().encode())
                digest.update(file.read_bytes())
    for file in sorted((Path(base) / "output/assets/local").glob("*.svg")):
        digest.update(contained(base, file).read_bytes())
    return digest.hexdigest()


def snapshot_materials(base, filenames, resume=False, directory="input/materials"):
    result, names = [], set()
    for filename in filenames:
        source = Path(filename).expanduser().resolve()
        if not source.is_file():
            raise ValueError("教材不存在: " + str(source))
        name = safe_name(source.name)
        if name.casefold() in names:
            raise ValueError("教材文件名重复，请重命名: " + name)
        names.add(name.casefold())
        if name.casefold() == "index.json":
            raise ValueError("index.json 是输入索引保留名称，请重命名素材")
        target = contained(base, Path(base) / directory / name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target:
            if resume and target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError("教材已改变，请创建新项目而不是复用缓存")
            if not target.exists() or not resume:
                shutil.copy2(source, target)
        result.append(str(target))
    if resume and not result:
        index = Path(base) / directory / "index.json"
        if index.is_file():
            order = json.loads(index.read_text(encoding="utf-8"))["files"]
            result = [str(contained(base, Path(base) / directory / name)) for name in order]
        else:
            root = Path(base) / directory
            if not root.is_dir():
                root = Path(base) / "materials"
            result = [str(contained(base, file)) for file in sorted(root.iterdir()) if file.is_file() and file.name != "index.json"]
    if not resume:
        write_json(Path(base) / directory / "index.json", {"files": [Path(file).name for file in result]})
    return result


def archive_resource(base, name, data, color="#287D68"):
    name = safe_name(name)
    suffix = Path(name).suffix.lower()
    if suffix not in RESOURCE_SUFFIXES or not data or len(data) > 50 * 1024 * 1024:
        raise ValueError("资源格式不支持、为空或超过 50MB: " + name)
    if suffix == ".svg":
        from icon_assets import safe_svg
        data = safe_svg(data.decode("utf-8-sig"), color).encode("utf-8")
        relative = Path("assets/local") / name
    elif suffix == ".py":
        relative = Path("code/svg") / name
    else:
        relative = Path("input/references") / name
    target = contained(base, Path(base) / relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def copy_project_inputs(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    for directory in ("prompts", "input", "code/runtime", "code/svg", "assets/local", "output/assets/local"):
        for file in sorted((source / directory).rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                contained(source, file)
                target = contained(destination, destination / file.relative_to(source))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)


def local_assets(base):
    roots = [Path(base) / "assets/local", Path(base) / "output/assets/local"]
    files = [file for root in roots if root.is_dir() for file in sorted(root.glob("*.svg"))]
    return [{"key": "local_" + file.stem, "path": str(contained(base, file)), "credit": "用户提供素材: " + file.name, "license": "发布前确认用户素材授权", "source": "local"} for file in files]


def restore_credentials(snapshot, current):
    if isinstance(snapshot, list):
        return [restore_credentials(item, current[index] if isinstance(current, list) and index < len(current) else {}) for index, item in enumerate(snapshot)]
    if not isinstance(snapshot, dict):
        return copy.deepcopy(current) if snapshot == "<redacted>" else snapshot
    current = current if isinstance(current, dict) else {}
    return {key: restore_credentials(value, current.get(key, {})) for key, value in snapshot.items()}


def needs_credentials(value):
    if isinstance(value, dict):
        return any(needs_credentials(item) for item in value.values())
    if isinstance(value, list):
        return any(needs_credentials(item) for item in value)
    return value == "<redacted>"


def restore_project_config(base, current, updates=None):
    from configuration import merge
    snapshot = json.loads((Path(base) / "settings.json").read_text(encoding="utf-8-sig"))
    snapshot = merge(snapshot, updates or {})
    previous_effective, current_effective = resolve_config(snapshot), resolve_config(current)
    for role in ("text", "vision", "tts"):
        settings = previous_effective.get(role, {})
        if needs_credentials(settings) and any(settings.get(key) != current_effective.get(role, {}).get(key) for key in ("base_url", "url")):
            raise ValueError("项目服务地址与当前凭证配置不一致；请恢复原服务地址或创建新版本")
    return restore_credentials(snapshot, current)
