"""Optional isolated faster-whisper worker; runs with CPU/int8, no API key or Codex."""
import argparse
import json
import time
from pathlib import Path

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("audio"); p.add_argument("output"); p.add_argument("--model", default="small"); p.add_argument("--cache", default=".cache/whisper")
    a = p.parse_args()
    from faster_whisper import WhisperModel
    start = time.perf_counter()
    model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=8, download_root=a.cache)
    import soundfile as sf
    audio, rate = sf.read(a.audio, dtype="float32")
    if rate != 16000 or audio.ndim != 1:
        raise ValueError("CPU worker expects mono 16 kHz WAV; use the ingestion service to normalize media")
    segments, info = model.transcribe(audio, language="zh", vad_filter=True, beam_size=5)
    result = {"language": info.language, "segments": [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments], "elapsed_seconds": time.perf_counter() - start, "device": "cpu", "compute_type": "int8"}
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
