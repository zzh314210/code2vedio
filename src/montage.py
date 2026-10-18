"""Deterministic archived-footage and music composition."""

import math
from pathlib import Path

import av

from media import ffmpeg_binary, probe, run_command


def number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"Invalid montage {label}")
    return float(value)


def source_file(name, sources, kind):
    matches = [item for item in sources if item.get("name") == name and item.get("type") == kind]
    if len(matches) != 1:
        raise ValueError(f"Montage source must uniquely identify an archived {kind}: {name}")
    path = Path(matches[0]["path"])
    if not path.is_file():
        raise ValueError(f"Missing montage source: {name}")
    return path


def compose_media(video, audio, destination_video, destination_audio, duration, settings, sources):
    if not settings:
        return video, audio
    if not isinstance(settings, dict) or set(settings) - {"clips", "music"}:
        raise ValueError("montage supports only clips and music")
    duration = number(duration, "duration", 0.001)
    clips = settings.get("clips", [])
    if not isinstance(clips, list) or len(clips) > 32:
        raise ValueError("montage.clips must have at most 32 entries")
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        width, height = stream.width, stream.height
        fps = float(stream.average_rate or 30)
    current_video = video
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or set(clip) - {"source", "start", "duration", "source_start"}:
            raise ValueError("Invalid montage clip")
        source = source_file(clip.get("source"), sources, "video")
        start = number(clip.get("start", 0), "clip.start")
        length = number(clip.get("duration"), "clip.duration", 0.001)
        offset = number(clip.get("source_start", 0), "clip.source_start")
        if start + length > duration + 0.01 or offset + length > probe(source)["duration"] + 0.01:
            raise ValueError("Montage clip exceeds source or output duration")
        target = Path(destination_video).with_name(f"montage_{index:03}.mp4")
        graph = (f"[0:v]setpts=PTS-STARTPTS[base];"
                 f"[1:v]trim=start={offset}:duration={length},setpts=PTS-STARTPTS+{start}/TB,"
                 f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},setsar=1[clip];"
                 f"[base][clip]overlay=eof_action=pass:enable='gte(t,{start})*lt(t,{start + length})'[out]")
        run_command([ffmpeg_binary(), "-y", "-i", str(current_video), "-i", str(source),
                     "-filter_complex", graph, "-map", "[out]", "-an", "-t", str(duration),
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)])
        current_video = target
    if clips:
        Path(current_video).replace(destination_video)
        current_video = destination_video
    current_audio = audio
    music = settings.get("music")
    if music is not None:
        if not isinstance(music, dict) or set(music) - {"source", "volume"}:
            raise ValueError("Invalid montage.music")
        source = source_file(music.get("source"), sources, "audio")
        volume = number(music.get("volume", 0.15), "music.volume")
        if volume > 1:
            raise ValueError("music.volume must be between zero and one")
        graph = f"[1:a]volume={volume}[music];[0:a][music]amix=inputs=2:duration=first:normalize=0[out]"
        run_command([ffmpeg_binary(), "-y", "-i", str(audio), "-stream_loop", "-1", "-i", str(source),
                     "-filter_complex", graph, "-map", "[out]", "-t", str(duration),
                     "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(destination_audio)])
        current_audio = destination_audio
    return current_video, current_audio
