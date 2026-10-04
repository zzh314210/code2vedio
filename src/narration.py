import asyncio
import base64
import re
import time

import edge_tts
import httpx
from openai import OpenAI

from configuration import validate_endpoint
from media import pcm_audio, silence


def fill_template(value, variables):
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace("{" + key + "}", str(replacement))
        return value
    if isinstance(value, dict):
        return {key: fill_template(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [fill_template(item, variables) for item in value]
    return value


class Narrator:
    def __init__(self, settings):
        self.settings = settings
        self.provider = settings.get("provider", "edge")
        if self.provider not in ("edge", "openai", "http", "none"):
            raise ValueError("tts.provider 必须是 edge / openai / http / none")
        if self.provider == "openai":
            validate_endpoint(settings.get("base_url"))
            if not settings.get("api_key") or not settings.get("model"):
                raise ValueError("OpenAI TTS 需要配置 api_key、model 和 voice")
            self.client = OpenAI(api_key=settings["api_key"], base_url=settings["base_url"], timeout=float(settings.get("timeout", 120)), max_retries=int(settings.get("max_retries", 2)))
        if self.provider == "http":
            validate_endpoint(settings.get("url"))
            if not isinstance(settings.get("payload"), dict):
                raise ValueError("HTTP TTS 需要配置 payload 模板")

    def synthesize(self, text, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.provider == "none":
            duration = max(2.0, len(text) / 4.5)
            silence(destination, duration)
            return {"duration": duration, "provider": "none", "silent": True}
        temporary = destination.with_suffix(".raw.mp3")
        subtitles = []
        if self.provider == "edge":
            failure = None
            for attempt in range(int(self.settings.get("max_retries", 2)) + 1):
                try:
                    subtitles = asyncio.run(asyncio.wait_for(self.edge_audio(text, temporary), timeout=float(self.settings.get("timeout", 120))))
                    failure = None
                    break
                except Exception as error:
                    failure = error
                    if attempt < int(self.settings.get("max_retries", 2)):
                        time.sleep(2 ** attempt)
            if failure:
                raise RuntimeError("Edge TTS 请求失败；检查网络，或改用 openai/http TTS") from failure
        elif self.provider == "openai":
            with self.client.audio.speech.with_streaming_response.create(
                model=self.settings["model"], voice=self.settings["voice"], input=text,
                response_format="mp3", speed=float(self.settings.get("speed", 1)), extra_body=self.settings.get("extra_body", {}),
            ) as response:
                response.stream_to_file(temporary)
        else:
            variables = {"text": text, "voice": self.settings.get("voice", ""), "model": self.settings.get("model", ""), "api_key": self.settings.get("api_key", ""), "speed": self.settings.get("speed", 1)}
            headers = fill_template(self.settings.get("headers", {}), variables)
            payload = fill_template(self.settings["payload"], variables)
            with httpx.Client(timeout=float(self.settings.get("timeout", 120))) as client:
                response = client.post(self.settings["url"], headers=headers, json=payload)
                response.raise_for_status()
                if self.settings.get("audio_base64_field"):
                    result = response.json()
                    for field in self.settings["audio_base64_field"].split("."):
                        result = result[field]
                    audio = base64.b64decode(result, validate=True)
                else:
                    audio = response.content
                if not audio:
                    raise ValueError("HTTP TTS 返回空音频")
                temporary.write_bytes(audio)
        duration = pcm_audio(temporary, destination)
        if not subtitles:
            subtitles = self.fallback_subtitles(text, duration)
        for index, cue in enumerate(subtitles):
            next_start = subtitles[index + 1]["start"] if index + 1 < len(subtitles) else duration
            cue["end"] = min(cue["end"], next_start, duration)
        return {"duration": duration, "provider": self.provider, "silent": False, "subtitles": subtitles}

    async def edge_audio(self, text, destination):
        subtitles = []
        communicator = edge_tts.Communicate(text, self.settings["voice"], rate=self.settings.get("rate", "+0%"), boundary="SentenceBoundary")
        with destination.open("wb") as audio:
            async for chunk in communicator.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                    subtitles.append({"start": chunk["offset"] / 10_000_000, "end": (chunk["offset"] + chunk["duration"]) / 10_000_000, "text": chunk["text"]})
        return subtitles

    @staticmethod
    def fallback_subtitles(text, duration):
        pieces = [piece.strip() for piece in re.split(r"(?<=[。！？；])|(?<=[，、])", text) if piece.strip()]
        if not pieces:
            pieces = [text]
        weights = [max(1, len(piece)) for piece in pieces]
        total = sum(weights)
        cursor = 0.0
        result = []
        for index, piece in enumerate(pieces):
            end = duration if index == len(pieces) - 1 else cursor + duration * weights[index] / total
            result.append({"start": cursor, "end": end, "text": piece})
            cursor = end
        return result
