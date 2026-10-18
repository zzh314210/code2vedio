import hashlib
import json
from pathlib import Path

from openai import OpenAI

from configuration import public_config, validate_endpoint


def transcribe_reference(source, settings, cache_directory=None):
    validate_endpoint(settings.get("base_url"))
    if not settings.get("api_key") or not settings.get("model"):
        raise ValueError("Audio reference transcription requires api_key and model")
    source = Path(source)
    payload = {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "settings": public_config(settings)}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    cache = Path(cache_directory) / (fingerprint + ".json") if cache_directory else None
    if cache and cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))["text"]
    client = OpenAI(api_key=settings["api_key"], base_url=settings["base_url"], timeout=float(settings.get("timeout", 120)), max_retries=int(settings.get("max_retries", 0)))
    try:
        with source.open("rb") as audio:
            result = client.audio.transcriptions.create(model=settings["model"], file=audio)
        text = result.text
    finally:
        client.close()
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Audio reference transcription returned empty text")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(".tmp")
        temporary.write_text(json.dumps({"text": text, "fingerprint": fingerprint}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cache)
    return text
