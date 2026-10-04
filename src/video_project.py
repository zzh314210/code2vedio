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


PROJECTS = ROOT / "projects"
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
    for directory in ("prompts", "materials", "examples", "code/runtime/extensions"):
        for file in sorted((source / directory).rglob("*")):
            if not file.is_file() or "__pycache__" in file.parts:
                continue
            contained(source, file)
            if directory == "prompts" and (file.parent != source / "prompts" or file.name not in {name + ".txt" for name in PROMPT_NAMES}):
                continue
            if directory == "materials" and file.suffix.lower() not in {".md", ".markdown", ".pdf"}:
                continue
            target = contained(destination, destination / file.relative_to(source))
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
    for name in ("materials", "examples", "prompts", "code/runtime", "code/svg", "output"):
        contained(base, base / name).mkdir(parents=True, exist_ok=True)
    metadata = base / "project.json"
    if not metadata.exists():
        identity = re.search(r"--([a-f0-9]{12})$", base.name)
        write_json(metadata, {"schema_version": 1, "id": identifier or (identity[1] if identity else uuid.uuid4().hex[:12]), "topic": topic, "parent": parent, "created_at": datetime.now().isoformat(timespec="seconds"), "layout": {"materials": "materials", "examples": "examples", "prompts": "prompts", "code": "code", "output": "output"}})
    for name, template in TEMPLATES.items():
        target = contained(base, base / "prompts" / (name + ".txt"))
        if not target.exists():
            target.write_text(template, encoding="utf-8")
    requirements = base / "prompts/requirements.json"
    if not requirements.exists():
        write_json(requirements, config.get("course", {}))
    for name in ("scene_runtime.py", "project_extensions.py"):
        target = contained(base, base / "code/runtime" / name)
        if not target.exists():
            shutil.copy2(ROOT / "src" / name, target)
    if not (base / "code/runtime/extensions.json").exists():
        write_json(base / "code/runtime/extensions.json", {})
    read_extensions(base / "code/runtime")
    if not (base / "settings.json").exists():
        write_json(base / "settings.json", public_config(config))
    documentation = {
        "examples/README.md": "# 本视频的例题与参考示例\n\n请在这里保存本课程的例题文档、设计参考和示例代码。需要模型读取的 Markdown/PDF，必须作为教材上传或传入 --material；此目录不会被自动当成模型指令。不要依赖全局 examples 中可变的课程文件。\n",
        "code/svg/README.md": "# 本视频的 SVG 绘制源码\n\n自绘 SVG 的 Python 源码可通过资源上传或 --resource 归档到这里。上传源码只做归档，不会自动执行。SVG 本体位于 output/assets/local；下载图标的 SVG 本体及来源位于 output/assets 和 ATTRIBUTION.md，下载图标不一定有可提供的生成程序。\n",
        "README.md": f"# 视频项目：{topic}\n\n本目录是一个独立视频项目。\n\n- project.json：标题、项目 ID 和父版本。\n- settings.json：本项目配置快照，密钥已脱敏，运行时从当前凭证配置恢复。\n- prompts/：公共规则、四阶段完整模板、requirements.json 课程要求。\n- materials/：实际使用的原始 Markdown/PDF 副本。\n- examples/：本课程例题和设计参考。\n- code/runtime/：本项目实际使用的绘图运行代码快照。\n- code/svg/：本项目自绘 SVG 源码（如已提供）。\n- output/：大纲、分镜、音频、素材、Manim 源码、日志、视频和字幕。\n- output/requests/：实际提交给模型的提示词记录（含教材选段）。\n\nWeb 编辑会创建独立新项目版本，旧目录保留。修改提示词、教材或代码后不要续用旧缓存；创建新版本。不要把运行目录直接公开，教材和提示词可能是私有内容。\n",
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
    for directory in ("prompts", "examples", "code/runtime", "code/svg"):
        for file in sorted((Path(base) / directory).rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                contained(base, file)
                digest.update(file.relative_to(base).as_posix().encode())
                digest.update(file.read_bytes())
    for file in sorted((Path(base) / "output/assets/local").glob("*.svg")):
        digest.update(contained(base, file).read_bytes())
    return digest.hexdigest()


def snapshot_materials(base, filenames, resume=False):
    result, names = [], set()
    for filename in filenames:
        source = Path(filename).expanduser().resolve()
        if not source.is_file():
            raise ValueError("教材不存在: " + str(source))
        name = safe_name(source.name)
        if name.casefold() in names:
            raise ValueError("教材文件名重复，请重命名: " + name)
        names.add(name.casefold())
        target = contained(base, Path(base) / "materials" / name)
        if source != target:
            if resume and target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError("教材已改变，请创建新项目而不是复用缓存")
            if not target.exists() or not resume:
                shutil.copy2(source, target)
        result.append(str(target))
    if resume and not result:
        index = Path(base) / "materials/index.json"
        if index.is_file():
            order = json.loads(index.read_text(encoding="utf-8"))["files"]
            result = [str(contained(base, Path(base) / "materials" / name)) for name in order]
        else:
            result = [str(contained(base, file)) for file in sorted((Path(base) / "materials").iterdir()) if file.suffix.lower() in (".md", ".markdown", ".pdf")]
    if not resume:
        write_json(Path(base) / "materials/index.json", {"files": [Path(file).name for file in result]})
    return result


def archive_resource(base, name, data, color="#287D68"):
    name = safe_name(name)
    suffix = Path(name).suffix.lower()
    if suffix not in RESOURCE_SUFFIXES or not data or len(data) > 50 * 1024 * 1024:
        raise ValueError("资源格式不支持、为空或超过 50MB: " + name)
    if suffix == ".svg":
        from icon_assets import safe_svg
        data = safe_svg(data.decode("utf-8-sig"), color).encode("utf-8")
        relative = Path("output/assets/local") / name
    elif suffix == ".py":
        relative = Path("code/svg") / name
    else:
        relative = Path("examples") / name
    target = contained(base, Path(base) / relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def copy_project_inputs(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    for directory in ("prompts", "examples", "code/runtime", "code/svg", "output/assets/local"):
        for file in sorted((source / directory).rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                contained(source, file)
                target = contained(destination, destination / file.relative_to(source))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)


def local_assets(base):
    return [{"key": "local_" + file.stem, "path": str(contained(base, file)), "credit": "用户提供素材: " + file.name, "license": "发布前确认用户素材授权", "source": "local"} for file in sorted((Path(base) / "output/assets/local").glob("*.svg"))]


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
