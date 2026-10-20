"""Local background music: immutable project inputs and narration-first mixing."""
import math
from pathlib import Path

from media import ffmpeg_binary, run_command, probe

DEFAULT_VOLUME = .16
MAX_VOLUME = .5
PROJECT_AUDIO = 'input/background_music/audio.m4a'


def validate_volume(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= MAX_VOLUME:
        raise ValueError('背景音乐音量应在 0% 至 50% 之间。')
    return value


def normalize_upload(source, destination):
    """Decode only local audio containers; playlists and external protocols are forbidden."""
    try:
        run_command([
            ffmpeg_binary(), '-nostdin', '-v', 'error', '-y', '-threads', '2', '-filter_threads', '1',
            '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mp3,wav,ogg,flac,aac,mov',
            '-i', str(source), '-map', '0:a:0', '-vn', '-sn', '-dn', '-t', '901',
            '-af', 'loudnorm=I=-18:TP=-2:LRA=9', '-ar', '48000', '-ac', '2',
            '-c:a', 'aac', '-threads', '2', '-b:a', '160k', '-map_metadata', '-1', '-movflags', '+faststart', str(destination),
        ], timeout=120)
        duration = probe(destination)['duration']
        if not 1 <= duration <= 900:
            raise ValueError('背景音乐请使用 1 秒至 15 分钟的音频。')
        return duration
    except Exception as error:
        Path(destination).unlink(missing_ok=True)
        if isinstance(error, ValueError) and str(error).startswith('背景音乐请'):
            raise
        raise ValueError('无法读取这份音乐，请上传有效的 MP3、WAV、M4A、OGG 或 FLAC 音频。') from error


def mix_background_music(narration, music, destination, duration, volume=DEFAULT_VOLUME):
    volume = validate_volume(volume)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('混音时长无效。')
    # Level the voice first so both quiet TTS and uploaded tracks have predictable balance.
    # The music starts at zero, repeats for the entire film, and ducks around speech.
    fade = min(.8, duration / 4)
    filters = (
        f'[0:a]loudnorm=I=-16:TP=-2:LRA=9,aresample=48000,'
        f'aformat=channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS,asplit=2[voice][side];'
        f'[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={duration},asetpts=PTS-STARTPTS,'
        f'volume={volume},afade=t=in:d={fade},afade=t=out:st={max(0,duration-fade)}:d={fade}[music];'
        '[music][side]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=350:makeup=1[ducked];'
        '[voice][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0:latency=1[out]'
    )
    run_command([ffmpeg_binary(), '-nostdin', '-v', 'error', '-y', '-threads', '2', '-filter_complex_threads', '1', '-i', str(narration),
                 '-stream_loop', '-1', '-i', str(music), '-filter_complex', filters,
                 '-map', '[out]', '-t', str(duration), '-ar', '48000', '-ac', '2',
                 '-c:a', 'pcm_s16le', str(destination)], timeout=max(120, int(duration) * 2))
    if abs(probe(destination)['duration'] - duration) > .05:
        raise ValueError('背景音乐混音时长异常。')
    return Path(destination)


def compose_background_music(project, audio, output, duration, settings):
    if not settings.get('enabled'):
        return audio
    project, output = Path(project).resolve(), Path(output)
    # The API freezes every selection here. Relative paths survive project revisions.
    source = (project / PROJECT_AUDIO).resolve()
    if not source.is_relative_to(project) or not source.is_file():
        raise ValueError('本项目的背景音乐文件缺失，请重新选择音乐后生成。')
    mixed = mix_background_music(audio, source, output / 'background_mix.wav', duration,
                                 settings.get('volume', DEFAULT_VOLUME))
    credit = settings.get('credit', '')
    if credit:
        (output / 'music-credit.txt').write_text(credit + '\n', encoding='utf8')
    return mixed
