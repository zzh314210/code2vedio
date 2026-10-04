import math
import os
import shutil
import subprocess
from pathlib import Path

import av
import imageio_ffmpeg


def ffmpeg_binary():
    configured = os.getenv("C2V_FFMPEG")
    if configured:
        if not Path(configured).is_file():
            raise ValueError("C2V_FFMPEG 指向的程序不存在")
        return configured
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def run_command(arguments, timeout=300, cwd=None):
    try:
        result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as failure:
        raise RuntimeError(f"子进程超时（{timeout}s）: {arguments[0]}") from failure
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-10000:])
    return result.stdout


def probe(filename):
    with av.open(str(filename)) as container:
        streams = [{"type": stream.type, "duration": float(stream.duration * stream.time_base) if stream.duration is not None else None} for stream in container.streams]
        duration = float(container.duration / av.time_base) if container.duration else max((item["duration"] or 0 for item in streams), default=0)
    if duration <= 0 or not math.isfinite(duration):
        raise ValueError(f"无法读取媒体时长: {filename}")
    return {"duration": duration, "streams": streams}


def pcm_audio(source, destination):
    run_command([ffmpeg_binary(), "-y", "-i", str(source), "-vn", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(destination)])
    return probe(destination)["duration"]


def silence(destination, duration):
    run_command([ffmpeg_binary(), "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(duration), "-c:a", "pcm_s16le", str(destination)])


def fit_audio(source, destination, duration):
    run_command([ffmpeg_binary(), "-y", "-i", str(source), "-af", "apad", "-t", str(duration), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(destination)])


def concat(files, destination, audio=False):
    listing = destination.with_suffix(".concat.txt")
    listing.write_text("\n".join("file '" + Path(file).resolve().as_posix().replace("'", "'\\''") + "'" for file in files), encoding="utf-8")
    encoding = ["-c:a", "pcm_s16le"] if audio else ["-c", "copy"]
    run_command([ffmpeg_binary(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing), *encoding, str(destination)])


def mux(video, audio, subtitles, destination, duration):
    run_command([
        ffmpeg_binary(), "-y", "-i", str(video), "-i", str(audio), "-i", str(subtitles),
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-c:s", "mov_text", "-metadata:s:s:0", "language=zho", "-t", str(duration), "-movflags", "+faststart", str(destination),
    ])


def sample_frames(video, directory, count=6):
    directory.mkdir(parents=True, exist_ok=True)
    duration = probe(video)["duration"]
    frames = []
    for index in range(count):
        frame = directory / f"frame_{index:03}.jpg"
        position = duration * (index + 0.5) / count
        run_command([ffmpeg_binary(), "-y", "-ss", str(position), "-i", str(video), "-frames:v", "1", "-vf", "scale=960:-2", str(frame)])
        if not frame.is_file():
            raise ValueError("FFmpeg 未能提取评审帧")
        frames.append(frame)
    return frames


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole, fraction = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{fraction:03}"


def write_subtitles(beats, destination):
    elapsed = 0.0
    blocks = []
    previous_end = 0.0
    for beat in beats:
        end = elapsed + beat["duration"]
        cues = beat.get("subtitles") or [{"start": 0, "end": beat["duration"], "text": beat["narration"]}]
        for cue in cues:
            start = max(previous_end, elapsed + max(0, cue["start"]))
            cue_end = min(end, elapsed + cue["end"])
            if cue_end > start:
                number = len(blocks) + 1
                blocks.append(f"{number}\n{timestamp(start)} --> {timestamp(cue_end)}\n{cue['text']}\n")
                previous_end = cue_end
        elapsed = end
    destination.write_text("\n".join(blocks), encoding="utf-8")
    return elapsed
