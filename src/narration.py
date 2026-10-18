import asyncio
import base64
import importlib.metadata
import re
import time
from urllib.parse import urlsplit, urlunsplit

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


class TTSProvider:
    """Extension contract for project-specific speech providers."""

    name = "custom"

    def __init__(self, settings):
        self.settings = settings

    def synthesize(self, text, destination):
        raise NotImplementedError


TTS_PROVIDERS = {}


class QwenAudioProvider(TTSProvider):
    name = "qwen_audio"

    def __init__(self, settings):
        super().__init__(settings)
        validate_endpoint(settings.get("base_url"))
        if not settings.get("api_key") or not settings.get("model") or not settings.get("voice"):
            raise ValueError("Qwen Audio TTS requires api_key, model and voice")
        parsed = urlsplit(settings["base_url"])
        self.url = urlunsplit((parsed.scheme, parsed.netloc, "/api/v1/services/audio/tts/SpeechSynthesizer", "", ""))

    def synthesize(self, text, destination):
        payload = {"model": self.settings["model"], "input": {"text": text, "voice": self.settings["voice"], "format": "wav", "sample_rate": 24000}}
        if self.settings.get("text_prompt"):
            payload["input"]["text_prompt"] = self.settings["text_prompt"]
        elif self.settings["model"].endswith("-tts-next"):
            payload["input"]["text_prompt"] = text
        with httpx.Client(timeout=float(self.settings.get("timeout", 120))) as client:
            response = client.post(self.url, headers={"Authorization": "Bearer " + self.settings["api_key"]}, json=payload)
            if not response.is_success:
                from configuration import sanitize_error
                raise ValueError("Qwen Audio TTS HTTP " + str(response.status_code) + ": " + sanitize_error(response.text[:1000], self.settings))
            audio = response.json().get("output", {}).get("audio", {})
            if audio.get("data"):
                data = base64.b64decode(audio["data"], validate=True)
            elif audio.get("url"):
                url = audio["url"]
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Invalid Qwen audio download URL")
                download = client.get(url)
                if not download.is_success:
                    raise ValueError("Qwen audio download HTTP " + str(download.status_code))
                data = download.content
            else:
                raise ValueError("Qwen Audio TTS returned no audio")
        if not data:
            raise ValueError("Qwen Audio TTS returned empty audio")
        temporary = destination.with_suffix(".qwen.raw.wav")
        try:
            temporary.write_bytes(data)
            duration = pcm_audio(temporary, destination)
            speed = float(self.settings.get("speed", 1.0))
            if speed != 1:
                if not .8 <= speed <= 1.25: raise ValueError("Speech speed must be .8..1.25")
                from media import run_command, ffmpeg_binary, probe
                adjusted = destination.with_suffix(".paced.wav")
                run_command([ffmpeg_binary(), "-y", "-i", str(destination), "-af", f"atempo={speed}", str(adjusted)])
                adjusted.replace(destination)
                duration = probe(destination)["duration"]
        finally:
            temporary.unlink(missing_ok=True)
        return {"duration": duration, "provider": self.name, "model": self.settings["model"], "silent": False, "subtitles": Narrator.fallback_subtitles(text, duration)}


from local_tts import GPTSoVITSProvider
TTS_PROVIDERS["qwen_audio"] = QwenAudioProvider
TTS_PROVIDERS["gpt_sovits"] = GPTSoVITSProvider


def register_tts_provider(name, factory):
    if not isinstance(name, str) or not name.strip() or not callable(factory):
        raise ValueError("TTS provider registration requires a name and callable factory")
    TTS_PROVIDERS[name.strip()] = factory


def list_tts_providers():
    installed = importlib.metadata.entry_points(group="code2video.tts")
    return sorted({"edge", "openai", "http", "none", *TTS_PROVIDERS, *(entry.name for entry in installed)})


class Narrator:
    def __init__(self, settings):
        self.settings = settings
        self.provider = settings.get("provider", "edge")
        self.plugin = None
        if self.provider not in ("edge", "openai", "http", "none"):
            factory = TTS_PROVIDERS.get(self.provider)
            if factory is None:
                entries = [entry for entry in importlib.metadata.entry_points(group="code2video.tts") if entry.name == self.provider]
                if len(entries) > 1:
                    raise ValueError(f"Multiple installed TTS plugins named {self.provider}")
                if entries:
                    factory = entries[0].load()
            if factory is None:
                raise ValueError(f"Unknown tts.provider {self.provider}; available: {', '.join(list_tts_providers())}")
            self.plugin = factory(settings)
            return
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
        if self.plugin is not None:
            return self.plugin.synthesize(text, destination)
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
