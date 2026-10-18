"""Generic video task input schema."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path

SCHEMA_VERSION = 1
REFERENCE_TYPES = {
    "text": {".txt", ".md", ".markdown", ".json", ".csv", ".py"},
    "document": {".pdf", ".doc", ".docx"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"},
    "svg": {".svg"},
    "video": {".mp4", ".mov", ".mkv", ".webm", ".avi"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"},
}


def infer_reference_type(filename: str | Path) -> str:
    suffix = Path(filename).suffix.lower()
    for reference_type, suffixes in REFERENCE_TYPES.items():
        if suffix in suffixes:
            return reference_type
    return "file"


def reference_record(path: str | Path, role: str = "reference", **extra) -> dict:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Reference does not exist: {source}")
    result = {
        "name": source.name,
        "path": str(source),
        "type": infer_reference_type(source),
        "role": role,
        "size": source.stat().st_size,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "mime": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
    }
    result.update(extra)
    return result


def normalize_task(prompt: str, style: str = "default", materials=None, references=None, config=None, tts=None, review=None) -> dict:
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Task prompt must not be empty")
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt": prompt,
        "style": style or "default",
        "materials": list(materials or []),
        "references": list(references or []),
        "config": dict(config or {}),
        "tts": dict(tts or {}),
        "review": dict(review or {}),
    }


def validate_task(task: dict) -> dict:
    if not isinstance(task, dict):
        raise ValueError("Task must be a JSON object")
    if task.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("Unsupported task schema_version")
    if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
        raise ValueError("task.prompt must be a non-empty string")
    for field in ("materials", "references"):
        if not isinstance(task.get(field, []), list):
            raise ValueError(f"task.{field} must be an array")
        if any(not isinstance(filename, str) or not filename.strip() for filename in task.get(field, [])):
            raise ValueError(f"task.{field} must contain non-empty path strings")
    for field in ("config", "tts", "review"):
        if not isinstance(task.get(field, {}), dict):
            raise ValueError(f"task.{field} must be an object")
    if not isinstance(task.get("style", "default"), str):
        raise ValueError("task.style must be a style ID string")
    return task


def load_task(filename: str | Path) -> dict:
    source = Path(filename).expanduser().resolve()
    return validate_task(json.loads(source.read_text(encoding="utf-8-sig")))
