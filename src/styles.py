"""Project-level visual style packages used by the video pipeline."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from configuration import ROOT, DEFAULTS, merge

STYLE_ROOT = ROOT / "style_skills" / "builtin"

@dataclass(frozen=True)
class StylePackage:
    id: str
    title: str
    description: str
    video: dict
    directory: Path
    policy: str
    version: str = "1.0.0"
    technical: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)

    def snapshot(self) -> dict:
        stages = {stage: style_stage_policy(self, stage) for stage in ("outline", "storyboard", "code", "review")}
        result = {"id": self.id, "version": self.version, "title": self.title, "description": self.description, "video": copy.deepcopy(self.video), "policy": self.policy, "stages": stages, "technical": copy.deepcopy(self.technical), "sources": copy.deepcopy(self.sources)}
        result["content_hash"] = snapshot_hash(result)
        return result


def snapshot_hash(snapshot):
    payload = {key: value for key, value in snapshot.items() if key != "content_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def technical_guidance():
    directory = ROOT / "style_skills" / "technical"
    return {stage: (directory / (stage + ".md")).read_text(encoding="utf-8") for stage in ("outline", "storyboard", "code", "review")}

def _read_package(directory: Path) -> StylePackage:
    metadata_file = directory / "style.json"
    if not metadata_file.is_file():
        raise ValueError(f"Style package is missing style.json: {directory}")
    metadata = json.loads(metadata_file.read_text(encoding="utf-8-sig"))
    identifier = metadata.get("id") or directory.name
    if identifier != directory.name:
        raise ValueError(f"Style package id does not match directory: {directory}")
    policy_file = directory / "prompts" / "policy.txt"
    policy = policy_file.read_text(encoding="utf-8-sig") if policy_file.is_file() else ""
    version = metadata.get("version", "1.0.0")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Style version must be semantic version x.y.z")
    return StylePackage(identifier, metadata.get("title", identifier), metadata.get("description", ""), metadata.get("video", {}), directory, policy.strip(), version, technical_guidance(), metadata.get("sources", []))

def list_styles() -> list[dict]:
    if not STYLE_ROOT.is_dir():
        return []
    result = []
    for directory in sorted(STYLE_ROOT.iterdir()):
        if directory.is_dir() and (directory / "style.json").is_file():
            package = _read_package(directory)
            result.append({"id": package.id, "title": package.title, "description": package.description})
    return result

def load_style(identifier: str | None) -> StylePackage:
    identifier = identifier or "default"
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
        raise ValueError("Invalid video style id")
    directory = STYLE_ROOT / identifier
    if directory.resolve().parent != STYLE_ROOT.resolve():
        raise ValueError("Style package path escapes registry")
    if not directory.is_dir():
        available = ", ".join(item["id"] for item in list_styles())
        raise ValueError(f"Unknown video style {identifier}; available: {available}")
    return _read_package(directory)

def style_video_config(config: dict, package: StylePackage) -> dict:
    explicit = config.get("video_overrides")
    if explicit is None:
        explicit = {key: value for key, value in config.get("video", {}).items() if value != DEFAULTS["video"].get(key)}
    video = merge(config.get("video", {}), package.video)
    video = merge(video, explicit)
    return merge(config, {"style": package.id, "video": video, "video_overrides": explicit})

def style_stage_policy(package: StylePackage, stage: str) -> str:
    stage_file = package.directory / "prompts" / f"{stage}.txt"
    if stage_file.is_file():
        return stage_file.read_text(encoding="utf-8-sig").strip()
    return package.policy
