import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from narration import Narrator


def run():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"output": {"audio": {"url": "https://audio.example/test.wav"}}})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"mock-audio")

    settings = {"provider": "qwen_audio", "base_url": "https://workspace.example/compatible-mode/v1", "api_key": "private-test-secret", "model": "qwen-audio-3.1-tts-next", "voice": "longanhuan_v3.6"}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with tempfile.TemporaryDirectory() as temporary, patch("narration.httpx.Client", return_value=client), patch("narration.pcm_audio", return_value=1.5):
        destination = Path(temporary) / "speech.wav"
        result = Narrator(settings).synthesize("Test speech", destination)
        assert result["duration"] == 1.5
        assert requests[0].url.path == "/api/v1/services/audio/tts/SpeechSynthesizer"
        import json
        payload = json.loads(requests[0].content)
        assert payload["input"]["text_prompt"] == "Test speech"
        assert payload["model"] == settings["model"]
        assert not destination.with_suffix(".qwen.raw.wav").exists()
    print("Qwen TTS protocol smoke passed")


if __name__ == "__main__":
    run()
