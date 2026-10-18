"""Search/read/index teaching sources with Agent Reach upstream tools, outside any agent host."""
import asyncio
from contextlib import contextmanager
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from teaching_research import extract_article, get_page, public_url, search_web

ROOT = Path(__file__).resolve().parents[1]


def binary(name):
    return shutil.which(name) or next((str(p) for p in (Path(sys.executable).parent / (name + ".exe"), Path(sys.executable).parent / name) if p.is_file()), None)


def command(arguments, timeout=35, cwd=None):
    result = subprocess.run(arguments, capture_output=True, encoding="utf8", errors="replace", timeout=timeout, cwd=cwd, shell=False, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if result.returncode:
        raise RuntimeError(f"{Path(arguments[0]).name} failed: " + (result.stderr or result.stdout)[-700:])
    if len(result.stdout) > 5_000_000:
        raise ValueError("Source tool output exceeds 5 MB")
    return result.stdout


def normalize_segments(segments):
    result = []
    for item in segments:
        start, end = float(item.get("start", item.get("from", 0))), float(item.get("end", item.get("to", 0)))
        text = str(item.get("text", item.get("content", ""))).strip()
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("Invalid transcript timestamps")
        if text and (not result or (text, start, end) != (result[-1]["text"], result[-1]["start"], result[-1]["end"])):
            result.append({"start": start, "end": end, "text": text})
    return sorted(result, key=lambda s: s["start"])


def parse_captions(text):
    if text.lstrip().startswith("{"):
        value = json.loads(text)
        return normalize_segments(value.get("body", value.get("segments", [])))
    def seconds(t):
        parts = t.replace(",", ".").split(":")
        return sum(float(x) * 60 ** i for i, x in enumerate(reversed(parts)))
    pattern = r"((?:\d+:)?\d{2}:\d{2}[.,]\d+)\s*-->\s*((?:\d+:)?\d{2}:\d{2}[.,]\d+)[^\n]*\n(.*?)(?=\n\s*\n|\Z)"
    return normalize_segments([{"start": seconds(a), "end": seconds(b), "text": BeautifulSoup(c, "html.parser").get_text(" ", strip=True)} for a, b, c in re.findall(pattern, text, re.S)])


def transcribe_local(path, settings, directory):
    if not settings.get("enabled"):
        raise RuntimeError("没有可读取字幕；CPU 转写尚未启用。可上传字幕/音频，或启用 teaching_research.asr。")
    from media import probe, ffmpeg_binary, run_command
    duration = probe(Path(path))["duration"]
    if duration > float(settings.get("max_seconds", 3600)):
        raise ValueError("Source audio exceeds configured ASR duration limit")
    wav = Path(directory) / "asr-input.wav"
    run_command([ffmpeg_binary(), "-y", "-i", str(path), "-vn", "-ar", "16000", "-ac", "1", str(wav)])
    output = Path(directory) / "transcript.json"
    python = settings.get("python") or sys.executable
    command([python, str(ROOT / "scripts/transcribe_cpu.py"), str(wav), str(output), "--model", settings.get("model", "small"), "--cache", str(settings.get("cache", Path(directory) / "models"))], timeout=float(settings.get("timeout", 3600)))
    return normalize_segments(json.loads(output.read_text(encoding="utf8"))["segments"])


class TeachingLibrary:
    def __init__(self, filename=None):
        self.path = Path(filename or ROOT / "references/teaching/library.sqlite3").resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, sha256 TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)")
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(id UNINDEXED,title,text,tokenize='trigram')")
            db.execute("CREATE TABLE IF NOT EXISTS failures (url TEXT PRIMARY KEY,error TEXT NOT NULL,updated_at TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def put(self, source):
        if not isinstance(source.get("text"), str) or len(source["text"].strip()) < 100:
            raise ValueError("Only substantive article/transcript content can enter the library")
        source = dict(source)
        source["id"] = "SRC" + hashlib.sha256(source["url"].encode()).hexdigest()[:16]
        source["sha256"] = hashlib.sha256(source["text"].encode()).hexdigest()
        source["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        source.setdefault("segments", [])
        with self.connect() as db:
            db.execute("DELETE FROM lessons_fts WHERE id=?", (source["id"],))
            db.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?)", (source["id"], source["url"], source["sha256"], source["title"], source["text"], json.dumps(source, ensure_ascii=False), source["retrieved_at"]))
            db.execute("INSERT INTO lessons_fts VALUES (?,?,?)", (source["id"], source["title"], source["text"]))
            db.execute("DELETE FROM failures WHERE url=?", (source["url"],))
        return source

    def failure(self, url, error):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO failures VALUES (?,?,?)", (url, str(error)[:1000], datetime.now(timezone.utc).isoformat()))

    def get(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM sources WHERE id=? OR url=?", (identity, identity)).fetchone()
        return json.loads(row[0]) if row else None

    def search(self, query, limit=10):
        terms = re.findall(r"[A-Za-z0-9]{3,}|[\u4e00-\u9fff]+", query)
        terms = [t for t in terms if len(t) >= 3][:12]
        with self.connect() as db:
            if terms:
                match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
                rows = db.execute("SELECT s.payload FROM lessons_fts f JOIN sources s ON s.id=f.id WHERE lessons_fts MATCH ? ORDER BY bm25(lessons_fts) LIMIT ?", (match, min(limit, 50))).fetchall()
            else:
                # Trigram cannot index two-character Chinese keywords; bounded LIKE fallback.
                rows = db.execute("SELECT payload FROM sources WHERE title LIKE ? OR text LIKE ? LIMIT ?", (f"%{query}%", f"%{query}%", min(limit, 50))).fetchall()
        return [json.loads(row[0]) for row in rows]

    def stats(self):
        with self.connect() as db:
            return {"sources": db.execute("SELECT count(*) FROM sources").fetchone()[0], "failures": db.execute("SELECT count(*) FROM failures").fetchone()[0]}


class TeachingSources:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.library = TeachingLibrary(self.settings.get("library"))

    def search(self, query, platform="web", limit=8):
        if platform == "library":
            return {"query": query, "backend": "sqlite-fts5", "results": self.library.search(query, limit)}
        if platform == "bilibili":
            executable = binary("bili")
            if not executable:
                raise RuntimeError("Install bilibili-cli to search Bilibili")
            raw = command([executable, "search", query, "--type", "video", "-n", str(limit), "--json"], self.settings.get("timeout", 30))
            value = json.loads(raw)
            entries = value.get("data", value.get("results", value)) if isinstance(value, dict) else value
            if isinstance(entries, dict): entries = entries.get("result", entries.get("items", []))
            if not isinstance(entries, list): raise ValueError("Unsupported bili search response")
            results = []
            for entry in entries:
                bvid = entry.get("bvid")
                url = entry.get("url") or entry.get("arcurl") or ("https://www.bilibili.com/video/" + bvid if bvid else "")
                if url: results.append({"title": BeautifulSoup(entry.get("title", ""), "html.parser").get_text(), "url": url, "query": query, "kind": "video", "metadata": entry})
            if not results: raise RuntimeError("Bilibili search returned no videos")
            return {"query": query, "backend": "agent-reach/bili-cli", "results": results}
        if platform not in ("web", "zhihu"):
            raise ValueError("platform must be web, bilibili, zhihu or library")
        return {**search_web(("site:zhihu.com " if platform == "zhihu" else "") + query, limit, self.settings.get("timeout", 20)), "backend": "sogou"}

    def read_article(self, url):
        # Agent Reach's ready-made Jina reader is especially useful for rich Zhihu pages.
        from agent_reach.channels.web import WebChannel
        errors = []
        if "zhihu.com" in (urlsplit(url).hostname or ""):
            try:
                text = WebChannel().read(url)
                if "Markdown Content:" not in text or len(text.split("Markdown Content:", 1)[1].strip()) < 400:
                    raise ValueError("Reader returned no substantive article")
                if any(x in text[:4000].lower() for x in ("requiring captcha", "access denied", "just a moment", "安全验证")):
                    raise ValueError("Reader returned a challenge page")
                title = re.search(r"^Title:\s*(.+)", text, re.M)
                images = [{"alt": alt, "url": image} for alt, image in re.findall(r"!\[([^\]]*)\]\((https?://[^)]+)\)", text)][:40]
                return {"url": url, "title": title[1] if title else url, "text": text.split("Markdown Content:", 1)[1][:48000], "images": images, "kind": "article", "backend": "agent-reach/jina-reader"}
            except Exception as error: errors.append(str(error))
        final, html = get_page(url, self.settings.get("timeout", 20))
        title, text = extract_article(html)
        soup = BeautifulSoup(html, "html.parser")
        from urllib.parse import urljoin
        images = [{"url": urljoin(final, n.get("data-src") or n.get("src")), "alt": n.get("alt", "")} for n in soup.select("article img,.article-content img,.RichText img") if n.get("data-src") or n.get("src")][:40]
        return {"url": final, "title": title, "text": text, "kind": "article", "images": images, "backend": "html/beautifulsoup", "reader_errors": errors}

    def read_bilibili(self, url, directory):
        match = re.search(r"BV[A-Za-z0-9]+", url)
        if not match: raise ValueError("请提供 Bilibili BV 视频完整链接")
        bvid, segments, errors = match[0], [], []
        title = bvid
        if binary("opencli"):
            try:
                output = command([binary("opencli"), "bilibili", "subtitle", bvid, "-f", "json"], 45)
                value = json.loads(output)
                if isinstance(value, dict): value = value.get("segments", value.get("data", []))
                if isinstance(value, list): segments = normalize_segments(value)
            except Exception as error: errors.append(str(error))
        async def native_subtitles():
            from bilibili_api import video
            from bili_cli.auth import _load_saved_credential
            v = video.Video(bvid=bvid, credential=_load_saved_credential())
            info = await v.get_info()
            try:
                subtitles = await v.get_subtitle(info["pages"][0]["cid"])
            except Exception as error:
                subtitles = {"error": str(error)}
            return info, subtitles
        metadata = {}
        if not segments:
            try:
                metadata, subs = asyncio.run(native_subtitles())
                title = metadata.get("title", bvid)
                if "error" in subs: errors.append(subs["error"])
                choices = subs.get("subtitles", subs.get("subtitle", {}).get("subtitles", []))
                choices.sort(key=lambda x: not str(x.get("lan", "")).startswith("zh"))
                if choices:
                    suburl = choices[0]["subtitle_url"]
                    _, body = get_page("https:" + suburl if suburl.startswith("//") else suburl, 20)
                    segments = parse_captions(body)
            except Exception as error: errors.append(str(error))
        if not segments and self.settings.get("asr", {}).get("enabled"):
            if metadata.get("duration", 0) > self.settings["asr"].get("max_seconds", 3600):
                raise ValueError("Video exceeds configured source duration limit")
            # Use the same upstream audio backend, with only explicitly saved Bilibili
            # credentials. Never invoke its automatic browser-cookie discovery.
            from bili_cli import client
            from bili_cli.auth import _load_saved_credential
            stream = asyncio.run(client.get_audio_url(bvid, credential=_load_saved_credential()))
            public_url(stream)
            import requests
            audio = Path(directory) / "source.m4a"
            size = 0
            with requests.get(stream, headers={"Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"}, stream=True, timeout=30) as response:
                response.raise_for_status()
                with audio.open("wb") as target:
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 256 * 1024 * 1024: raise ValueError("Source audio exceeds 256 MB")
                        target.write(chunk)
            segments = transcribe_local(audio, self.settings["asr"], directory)
        if not segments:
            raise RuntimeError("未取得实际字幕或转写，不能将视频标题/简介当成讲解。" + " | ".join(errors)[:700])
        return {"url": url, "title": title, "kind": "video", "segments": segments, "text": "\n".join(s["text"] for s in segments), "metadata": metadata, "backend": "agent-reach/bili-cli+subtitles/asr", "errors": errors}

    def ingest(self, url):
        public_url(url)
        try:
            with tempfile.TemporaryDirectory(prefix="c2v-teaching-") as directory:
                host = urlsplit(url).hostname or ""
                result = self.read_bilibili(url, directory) if host == "bilibili.com" or host.endswith(".bilibili.com") else self.read_article(url)
            return self.library.put(result)
        except Exception as error:
            self.library.failure(url, error)
            raise

    def ingest_local(self, path, source_url=None):
        path = Path(path).resolve()
        segments = []
        if path.suffix.lower() in (".vtt", ".srt", ".json"):
            segments = parse_captions(path.read_text(encoding="utf-8-sig"))
            text = "\n".join(x["text"] for x in segments)
        elif path.suffix.lower() in (".wav", ".mp3", ".m4a", ".mp4", ".mkv", ".webm"):
            with tempfile.TemporaryDirectory(prefix="c2v-asr-") as directory:
                segments = transcribe_local(path, self.settings.get("asr", {}), directory)
            text = "\n".join(x["text"] for x in segments)
        else: text = path.read_text(encoding="utf-8-sig")
        return self.library.put({"url": source_url or path.as_uri(), "title": path.name, "kind": "transcript" if segments else "article", "segments": segments, "text": text, "backend": "uploaded-material"})
