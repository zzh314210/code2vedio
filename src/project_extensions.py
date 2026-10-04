import json
import re
from pathlib import Path, PurePosixPath


def read_extensions(runtime):
    runtime = Path(runtime).resolve()
    manifest = (runtime / "extensions.json").resolve()
    if runtime not in manifest.parents:
        raise ValueError("扩展清单路径越界")
    if not manifest.is_file():
        return {}
    if manifest.stat().st_size > 200000:
        raise ValueError("扩展清单过大")
    entries = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(entries, dict):
        raise ValueError("扩展清单必须是名称到入口配置的 JSON 对象")
    for name, entry in entries.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or not isinstance(entry, dict):
            raise ValueError("非法扩展名称或配置")
        if set(entry) - {"file", "entrypoint", "description"}:
            raise ValueError("扩展配置仅支持 file/entrypoint/description")
        relative = entry.get("file", "")
        if not isinstance(relative, str) or "\\" in relative:
            raise ValueError("扩展文件须使用项目内相对路径")
        parts = PurePosixPath(relative)
        if parts.is_absolute() or ".." in parts.parts or len(parts.parts) < 2 or parts.parts[0] != "extensions" or parts.suffix != ".py":
            raise ValueError("扩展文件必须位于 code/runtime/extensions/*.py")
        target = (runtime / relative).resolve()
        extensions = runtime / "extensions"
        if runtime not in target.parents or extensions not in target.parents or not target.is_file():
            raise ValueError("扩展文件不存在或路径越界")
        entrypoint = entry.get("entrypoint", "")
        if not isinstance(entrypoint, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", entrypoint):
            raise ValueError("非法扩展入口函数名")
        description = entry.get("description", "")
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError("扩展说明必须是字符串且不超过 4000 字")
    return entries
