"""Per-account uploaded music and an explicitly licensed local preset catalog."""
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from background_music import normalize_upload, validate_volume, PROJECT_AUDIO
from video_project import write_json, safe_name
from storage_lifecycle import TTL

MAX_BYTES = 30 * 1024 * 1024


class BackgroundMusic:
    def __init__(self, root, private, user):
        self.root, self.private, self.user = Path(root), Path(private), user
        self.lock = threading.Lock()
        self.uploading = set()
        self.router = APIRouter()
        self.router.add_api_route('/api/music/uploads', self.list_uploads, methods=['GET'])
        self.router.add_api_route('/api/music/uploads', self.upload, methods=['POST'], status_code=201)
        self.router.add_api_route('/api/music/uploads/{identity}/audio', self.audio, methods=['GET'])
        self.router.add_api_route('/api/music/uploads/{identity}', self.delete, methods=['DELETE'])

    def directory(self):
        return self.private / 'music' / self.user()['id']

    def item(self, identity):
        if not re.fullmatch(r'[a-f0-9]{24}', identity):
            raise HTTPException(404, '音乐不存在。')
        directory = self.directory() / identity
        try:
            track = json.loads((directory / 'track.json').read_text(encoding='utf8'))
            if time.time()>=track.get('expires_at',track.get('created_at',0)+TTL):
                raise FileNotFoundError()
            if not (directory / 'audio.m4a').is_file():
                raise FileNotFoundError()
        except (OSError, ValueError):
            raise HTTPException(404, '音乐不存在，可能已移除。')
        return track, directory / 'audio.m4a'

    def list_uploads(self):
        tracks = []
        for metadata in self.directory().glob('*/track.json'):
            try:
                tracks.append(self.item(metadata.parent.name)[0])
            except HTTPException:
                continue
        return sorted(tracks, key=lambda t: t['created_at'], reverse=True)

    async def upload(self, file: UploadFile = File(...)):
        name = safe_name(file.filename or '我的音乐')
        if Path(name).suffix.lower() not in {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'}:
            raise HTTPException(400, '支持 MP3、WAV、M4A、OGG、FLAC 和 AAC 音频。')
        owner = self.user()['id']
        with self.lock:
            if owner in self.uploading:
                raise HTTPException(409, '上一份音乐仍在处理，请稍候。')
            if len(self.uploading) >= 2:
                raise HTTPException(429, '音乐处理繁忙，请稍后再上传。')
            if len(self.list_uploads()) >= 20:
                raise HTTPException(400, '最多保存 20 首音乐，请先移除不用的曲目。')
            self.uploading.add(owner)
        identity = uuid.uuid4().hex[:24]
        directory = self.directory() / identity
        try:
            directory.mkdir(parents=True, mode=0o700)
            source = directory / ('upload' + Path(name).suffix.lower())
            size = 0
            with source.open('wb') as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, '音乐文件请控制在 30 MB 以内。')
                    stream.write(chunk)
            duration = await run_in_threadpool(normalize_upload, source, directory / 'audio.m4a')
            source.unlink()
            track = {'id': identity, 'title': Path(name).stem, 'original_title': name,
                     'kind': 'upload', 'duration': round(duration, 2), 'created_at': time.time(), 'expires_at':time.time()+TTL,
                     'audio_url': f'/api/music/uploads/{identity}/audio', 'credit': ''}
            write_json(directory / 'track.json', track)
            return track
        except ValueError as error:
            shutil.rmtree(directory, ignore_errors=True)
            raise HTTPException(400, str(error))
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            await file.close()
            with self.lock:
                self.uploading.discard(owner)

    def audio(self, identity: str):
        _, source = self.item(identity)
        return FileResponse(source, media_type='audio/mp4')

    def delete(self, identity: str):
        with self.lock:
            _, source = self.item(identity)
            shutil.rmtree(source.parent)
        return {'ok': True}

    def cleanup(self):
        with self.lock:
            for directory in (self.private/'music').glob('*/*'):
                if directory.is_symlink() or not directory.is_dir() or directory.parent.name in self.uploading:continue
                metadata=directory/'track.json'
                try:
                    if not metadata.is_file():
                        if time.time()-directory.stat().st_mtime>TTL:shutil.rmtree(directory)
                        continue
                    track=json.loads(metadata.read_text())
                    if time.time()>=track.get('expires_at',track.get('created_at',0)+TTL):
                        shutil.rmtree(directory)
                except (OSError,ValueError):continue

    def select(self, enabled, track_id, upload_id, volume):
        if not enabled:
            return {'enabled': False}, None
        try:
            volume = validate_volume(volume)
        except (TypeError, ValueError):
            raise HTTPException(400, '背景音乐音量应在 0% 至 50% 之间。')
        if bool(track_id) == bool(upload_id):
            raise HTTPException(400, '请选择一首背景音乐，或先上传自己的音乐。')
        if upload_id:
            track, source = self.item(upload_id)
        else:
            tracks = json.loads((self.root / 'web/public/bgm/catalog.json').read_text())['tracks']
            track = next((item for item in tracks if item['id'] == track_id), None)
            if not track:
                raise HTTPException(400, '所选背景音乐已不可用，请重新选择。')
            source = self.root / 'web/public' / track['audio_url'].lstrip('/')
            if not source.is_file():
                raise HTTPException(503, '这首音乐暂不可用，请选择另一首。')
        return {**track, 'enabled': True, 'volume': volume}, source

    def freeze(self, settings, source, project):
        if source:
            target = Path(project) / PROJECT_AUDIO
            target.parent.mkdir(parents=True, exist_ok=True)
            with self.lock:
                if not source.is_file():
                    raise HTTPException(400, '音乐已移除，请重新选择。')
                shutil.copy2(source, target)
        write_json(Path(project) / 'input/background_music/selection.json', settings)
        return settings
