import copy
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "text": {
        "protocol": "responses", "base_url": "https://api.openai.com/v1",
        "api_key": "${OPENAI_API_KEY}", "model": "", "timeout": 180,
        "max_retries": 2, "max_tokens": 12000, "extra_body": {},
        "token_parameter": "max_completion_tokens",
    },
    "vision": {"enabled": False, "inherit_text": True, "frames": 6, "rounds": 1, "max_tokens": 2048, "timeout": 90, "max_retries": 0},
    "tts": {
        "provider": "edge", "voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%",
        "speed": 1.0, "timeout": 120, "max_retries": 2,
    },
    "video": {
        "quality": "medium", "font": "Microsoft YaHei", "fps": 30,
        "max_sections": 4, "max_beats": 5, "fix_attempts": 3,
        "render_timeout": 300, "pause_seconds": 0.3,
        "theme": "dark", "orientation": "landscape", "brand": "教学 · 可视化课堂",
        "narration_max_chars": 140, "caption_max_chars": 42, "subtitle_language": "zho",
    },
    "materials": {"max_chars": 24000, "max_file_mb": 50},
    "course": {"language": "中文", "instructions": "", "prompts": {}},
    "assets": {
        "enabled": False, "strategy": "first_success", "strict": False,
        "color": "#58C4DD", "max_per_section": 2, "timeout": 20,
        "sources": {
            "iconvaultkit": {"enabled": True, "url": "https://iconvaultkit.com/api/mcp", "collection": "lucide"},
            "infyicon": {"enabled": False, "url": "https://infyicon.com/mcp", "style": "outline"},
            "graphics_api_remotion": {"enabled": False, "providers": ["lucide", "phosphor"], "style": "regular"},
        },
    },
}

def merge(base, updates):
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result

def expand_env(value):
    if isinstance(value, str):
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", lambda match: os.getenv(match[1], ""), value)
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    return value

def load_config(filename=None, overrides=None, resolved=True):
    load_dotenv(ROOT / ".env", override=False)
    chosen = Path(filename).expanduser().resolve() if filename else ROOT / "config.local.json"
    if filename and not chosen.is_file():
        raise ValueError(f"配置文件不存在: {chosen}")
    updates = json.loads(chosen.read_text(encoding="utf-8-sig")) if chosen.is_file() else {}
    if not isinstance(updates, dict):
        raise ValueError("配置必须是 JSON 对象")
    config = merge(DEFAULTS, updates)
    for role, prefix in (("text", "C2V_TEXT"), ("vision", "C2V_VISION"), ("tts", "C2V_TTS")):
        for key in ("base_url", "api_key", "model", "protocol", "voice", "provider"):
            env_name = prefix + "_" + key.upper()
            if env_name in os.environ:
                config[role][key] = "${" + env_name + "}" if key == "api_key" else os.environ[env_name]
    config = merge(config, overrides or {})
    return resolve_config(config) if resolved else config


def resolve_config(config):
    config = expand_env(copy.deepcopy(config))
    if config["vision"].get("inherit_text", True):
        overrides = {key: value for key, value in config["vision"].items() if value not in (None, "")}
        config["vision"] = merge(config["text"], overrides)
    if config["tts"]["provider"] == "openai":
        for key in ("base_url", "api_key"):
            if not config["tts"].get(key):
                config["tts"][key] = config["text"].get(key)
    return config

def validate_endpoint(url):
    parsed = urlsplit(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("API URL 必须是 http(s) 地址，不允许 URL 中包含密码")
    if parsed.query or parsed.fragment:
        raise ValueError("API base_url 不允许 query/fragment；参数请放入 extra_body")

def validate_model(settings, role):
    if settings.get("protocol") not in ("responses", "chat_completions"):
        raise ValueError(f"{role}.protocol 只能是 responses 或 chat_completions")
    validate_endpoint(settings.get("base_url"))
    if not settings.get("model") or settings["model"].startswith("YOUR_"):
        raise ValueError(f"请配置 {role}.model 为你的服务实际支持的模型 ID")
    if not settings.get("api_key"):
        raise ValueError(f"请配置 {role}.api_key 或对应环境变量；本地无认证服务可填任意非空值")
    if settings.get("token_parameter", "max_completion_tokens") not in ("max_tokens", "max_completion_tokens"):
        raise ValueError("token_parameter 必须是 max_tokens 或 max_completion_tokens")
    if not isinstance(settings.get("extra_body", {}), dict):
        raise ValueError("extra_body 必须是 JSON 对象")

def secret_field(key):
    name = key.lower().replace("-", "_")
    return name in ("api_key", "authorization", "headers", "access_token", "refresh_token", "token", "secret", "password", "credentials") or name.endswith(("_api_key", "_secret", "_token"))


def public_config(value):
    if isinstance(value, dict):
        return {key: ("<redacted>" if secret_field(key) else public_config(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [public_config(item) for item in value]
    return value


def sanitize_error(message, config=None):
    secrets = []

    def collect(value, sensitive=False):
        if isinstance(value, dict):
            for key, item in value.items():
                collect(item, sensitive or secret_field(key))
        elif isinstance(value, list):
            for item in value:
                collect(item, sensitive)
        elif sensitive and isinstance(value, str) and len(value) >= 8:
            secrets.append(value)

    collect(expand_env(config or {}))
    text = str(message)
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return re.sub(r"(?i)\b(?:sk-[a-z0-9._-]+|bearer\s+[a-z0-9._-]+)", "<redacted>", text)
