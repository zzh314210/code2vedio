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


def run_command(arguments, timeout=300, cwd=None, env=None):
    try:
        result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
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


def prepend_audio_silence(source, destination, seconds):
    milliseconds = round(float(seconds) * 1000)
    if not 0 <= milliseconds <= 30000:
        raise ValueError("Audio lead-in must be between 0 and 30 seconds")
    run_command([ffmpeg_binary(), "-y", "-i", str(source), "-af", f"adelay={milliseconds}:all=1", "-c:a", "pcm_s16le", str(destination)])


def fit_audio(source, destination, duration):
    run_command([ffmpeg_binary(), "-y", "-i", str(source), "-af", "apad", "-t", str(duration), "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(destination)])


def concat(files, destination, audio=False):
    listing = destination.with_suffix(".concat.txt")
    listing.write_text("\n".join("file '" + Path(file).resolve().as_posix().replace("'", "'\\''") + "'" for file in files), encoding="utf-8")
    encoding = ["-c:a", "pcm_s16le"] if audio else ["-c", "copy"]
    run_command([ffmpeg_binary(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing), *encoding, str(destination)])


def mux(video, audio, subtitles, destination, duration, subtitle_language="zho", subtitle_mode="soft"):
    with av.open(str(video)) as container:
        stream = next(s for s in container.streams if s.type == "video")
        frame_rate = float(stream.base_rate or stream.average_rate)
        if subtitle_mode=='burn':width,height=stream.width,stream.height
    if not math.isfinite(frame_rate) or frame_rate <= 0:
        raise ValueError("Invalid final video frame rate")
    frame_count = max(1, round(duration * frame_rate))
    if subtitle_mode not in ('soft','burn','off'):raise ValueError('字幕模式无效')
    filters=f"fps={frame_rate},tpad=stop_mode=clone:stop_duration=1"
    if subtitle_mode=='burn':
        from subtitle_render import write_ass,filter_path
        ass=Path(destination).parent/'captions.ass';write_ass(subtitles,ass,width,height)
        filters+=",ass=filename='"+filter_path(ass)+"'"
    subtitle_input=[] if subtitle_mode=='off' else ['-i',str(subtitles)]
    subtitle_map=[] if subtitle_mode=='off' else ['-map','2:0','-c:s','mov_text','-metadata:s:s:0',f'language={subtitle_language}']
    run_command([
        ffmpeg_binary(), "-y", '-threads','2', "-i", str(video), "-i", str(audio), *subtitle_input,
        "-map", "0:v:0", "-map", "1:a:0", *subtitle_map,
        "-vf", filters, "-frames:v", str(frame_count),
        "-c:v", "libx264", '-threads','2', "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=9", "-ar", "48000",
        "-t", str(duration), "-movflags", "+faststart", str(destination),
    ])



def sample_frames(video, directory, count=6, positions=None):
    directory.mkdir(parents=True, exist_ok=True)
    duration = probe(video)["duration"]
    positions = [duration * (index + 0.5) / count for index in range(count)] if positions is None else positions
    if not 1 <= len(positions) <= 960 or any(not isinstance(t,(int,float)) or not math.isfinite(t) or not 0 <= t < duration for t in positions):
        raise ValueError('Frame positions must be finite and inside the video')
    frames = []
    for index,position in enumerate(positions):
        frame = directory / f"frame_{index:03}.jpg"
        run_command([ffmpeg_binary(), "-y", "-ss", str(position), "-i", str(video), "-frames:v", "1", "-vf", "scale=960:-2", str(frame)])
        if not frame.is_file():
            raise ValueError("FFmpeg 未能提取评审帧")
        frames.append(frame)
    (directory/'timestamps.json').write_text(__import__('json').dumps(positions),encoding='utf8')
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


def sample_beat_frames(video, directory, beats, count=12):
    """Sample every semantic beat, including the result of its motion."""
    directory.mkdir(parents=True, exist_ok=True)
    # Two per beat is the quality floor; avoid missing a short beat entirely.
    per_beat = max(2, math.ceil(count / len(beats)))
    positions = []
    cursor = 0.0
    for beat in beats:
        lead = float(beat.get('lead_in_seconds', 0))
        if lead > 0:
            positions.append(cursor + lead * .5)
        positions.extend(cursor + beat['duration'] * fraction for fraction in
                         [0.2 + 0.65 * i / max(1, per_beat - 1) for i in range(per_beat)])
        cursor += beat['duration']
    result = []
    for index, position in enumerate(positions):
        file = directory / f'frame_{index:03}.jpg'
        run_command([ffmpeg_binary(), '-y', '-ss', str(position), '-i', str(video),
                     '-frames:v', '1', '-vf', 'scale=1280:-2', str(file)])
        if not file.is_file(): raise ValueError('Review frame extraction failed')
        result.append(file)
    (directory / 'timestamps.json').write_text(__import__('json').dumps(positions), encoding='utf8')
    return result
