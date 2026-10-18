import csv
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader

from task_schema import infer_reference_type


TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".csv", ".py", ".yaml", ".yml"}


def page_numbers(specification, count):
    if not specification:
        return list(range(count))
    selected = set()
    for part in specification.split(","):
        match = re.fullmatch(r"\s*(\d+)(?:-(\d+))?\s*", part)
        if not match:
            raise ValueError("PDF 页码格式应为 1-3,5（从 1 开始）")
        start, end = int(match[1]), int(match[2] or match[1])
        if start < 1 or end < start or end > count:
            raise ValueError(f"PDF 页码超出范围 1-{count}: {part}")
        selected.update(range(start - 1, end))
    return sorted(selected)


def _read_text(file):
    suffix = file.suffix.lower()
    if suffix == ".json":
        value = json.loads(file.read_text(encoding="utf-8-sig"))
        return json.dumps(value, ensure_ascii=False, indent=2)
    if suffix == ".csv":
        with file.open("r", encoding="utf-8-sig", newline="") as stream:
            return "\n".join(" | ".join(row) for row in csv.reader(stream))
    return file.read_text(encoding="utf-8-sig")


def _source_record(file, role):
    data = file.read_bytes()
    return {
        "name": file.name,
        "path": str(file),
        "role": role,
        "type": infer_reference_type(file),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def load_materials(filenames, prompt, settings, pages=None, references=None, cache_directory=None):
    chunks = []
    sources = []
    visual_inputs = []
    entries = [(filename, "material") for filename in filenames]
    entries.extend((filename, "reference") for filename in (references or []))
    for filename, role in entries:
        file = Path(filename).expanduser().resolve()
        if not file.is_file():
            raise ValueError(f"输入素材不存在: {file}")
        if file.stat().st_size > float(settings.get("max_file_mb", 50)) * 1024 * 1024:
            raise ValueError(f"输入素材过大: {file.name}")
        record = _source_record(file, role)
        sources.append(record)
        suffix = file.suffix.lower()
        if suffix == ".pdf":
            reader = PdfReader(file)
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise ValueError(f"PDF 已加密，请先解密: {file.name}")
            extracted = 0
            for page in page_numbers(pages, len(reader.pages)):
                text = (reader.pages[page].extract_text() or "").strip()
                if text:
                    chunks.extend(split_text(text, f"{file.name}#p{page + 1}"))
                    extracted += 1
            if not extracted:
                record["note"] = "PDF 未提取到文本；已保留为外部参考元数据"
        elif suffix in TEXT_SUFFIXES:
            text = _read_text(file).strip()
            if text:
                chunks.extend(split_text(text, file.name))
            else:
                record["note"] = "文本文件为空"
        elif record["type"] == "audio" and settings.get("transcription", {}).get("enabled", False):
            from audio_references import transcribe_reference
            text = transcribe_reference(file, settings["transcription"], cache_directory)
            chunks.extend(split_text(text, file.name + "#transcript"))
            record["note"] = "Audio reference transcribed; verify transcript before publishing"
        else:
            record["note"] = "二进制素材不直接发送给文本模型；可供后续视觉、剪辑或人工参考"
        if record["type"] in {"image", "svg", "video", "audio"}:
            visual_inputs.append(record)

    budget = int(settings.get("max_chars", 24000))
    if budget < 1000:
        raise ValueError("materials.max_chars 至少为 1000")
    terms = set(re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2}", prompt))
    if sum(len(item["text"]) + len(item["source"]) + 10 for item in chunks) > budget:
        ranked = sorted(enumerate(chunks), key=lambda pair: -sum(pair[1]["text"].count(term) for term in terms))
        chosen = []
        remaining = budget
        for index, chunk in ranked:
            cost = len(chunk["text"]) + len(chunk["source"]) + 10
            if cost <= remaining:
                chosen.append(index)
                remaining -= cost
        selected = [chunk for index, chunk in enumerate(chunks) if index in chosen]
    else:
        selected = chunks
    context = "\n\n".join(f"[{chunk['source']}]\n{chunk['text']}" for chunk in selected)
    if visual_inputs:
        inventory = "\n".join(
            f"- {item['name']} ({item['type']}, {item['role']}, {item['size']} bytes)"
            for item in visual_inputs
        )
        context += ("\n\n" if context else "") + "<external_media_inventory>\n" + inventory + "\n</external_media_inventory>"
    return {
        "sources": sources,
        "selected_chunks": selected,
        "omitted_chunks": len(chunks) - len(selected),
        "visual_inputs": visual_inputs,
        "context": context,
    }


def split_text(text, source):
    lines = text.splitlines()
    chunks = []
    current = []
    start = 1
    size = 0
    for number, line in enumerate(lines, 1):
        for offset in range(0, max(1, len(line)), 1800):
            fragment = line[offset:offset + 1800]
            if size + len(fragment) > 2000 and current:
                chunks.append({"source": f"{source}:L{start}", "text": "\n".join(current)})
                current, size, start = [], 0, number
            current.append(fragment)
            size += len(fragment) + 1
    if current:
        chunks.append({"source": f"{source}:L{start}", "text": "\n".join(current)})
    return chunks
