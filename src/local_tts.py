"""GPT-SoVITS v2 API adapter. CPU service stays outside the video renderer environment."""
import math
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from configuration import validate_endpoint
from media import pcm_audio


class GPTSoVITSProvider:
    name = "gpt_sovits"

    def __init__(self, settings):
        self.settings = settings
        self.url = settings.get("url", "http://127.0.0.1:9880/tts")
        validate_endpoint(self.url)
        # The reference is a path on the TTS host, not uploaded silently.
        if not settings.get("ref_audio_path") or not str(settings.get("prompt_text", "")).strip():
            raise ValueError("GPT-SoVITS requires a fixed male-teacher reference audio path and its exact transcript")
        self.speed = float(settings.get("speed", 1.0))
        if not math.isfinite(self.speed) or not .8 <= self.speed <= 1.25:
            raise ValueError("Local speech speed must be .8..1.25")

    def synthesize(self, text, destination):
        payload = {"text": text, "text_lang": "zh", "ref_audio_path": self.settings["ref_audio_path"], "prompt_text": self.settings["prompt_text"], "prompt_lang": "zh", "text_split_method": "cut5", "batch_size": 1, "media_type": "wav", "streaming_mode": False, "speed_factor": self.speed, "seed": int(self.settings.get("seed", 37)), "parallel_infer": False}
        started = time.perf_counter()
        with httpx.Client(timeout=float(self.settings.get("timeout", 900))) as client:
            response = client.post(self.url, json=payload)
            if not response.is_success:
                raise RuntimeError("GPT-SoVITS HTTP " + str(response.status_code) + ": " + response.text[:600])
            data = response.content
        if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise ValueError("Local TTS returned no valid WAV audio")
        destination = Path(destination)
        temporary = destination.with_suffix(".sovits.raw.wav")
        try:
            temporary.write_bytes(data)
            duration = pcm_audio(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        from narration import Narrator
        elapsed = time.perf_counter() - started
        return {"duration": duration, "provider": self.name, "model": self.settings.get("model", "gpt-sovits-v2"), "silent": False, "voice": self.settings.get("voice", "male-teacher"), "synthesis_seconds": elapsed, "rtf": elapsed / duration, "timing_method": "estimated", "subtitles": Narrator.fallback_subtitles(text, duration)}
