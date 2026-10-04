import hashlib
import re
from pathlib import Path

from pypdf import PdfReader


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


def load_materials(filenames, topic, settings, pages=None):
    chunks = []
    sources = []
    for filename in filenames:
        file = Path(filename).expanduser().resolve()
        if not file.is_file():
            raise ValueError(f"教材不存在: {file}")
        if file.stat().st_size > float(settings.get("max_file_mb", 50)) * 1024 * 1024:
            raise ValueError(f"教材过大: {file.name}")
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        sources.append({"name": file.name, "sha256": digest})
        if file.suffix.lower() == ".pdf":
            reader = PdfReader(file)
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise ValueError(f"PDF 已加密，请先解密: {file.name}")
            for page in page_numbers(pages, len(reader.pages)):
                text = (reader.pages[page].extract_text() or "").strip()
                if not text:
                    raise ValueError(f"{file.name} 第 {page + 1} 页没有可提取文本（扫描件需先 OCR 或转换 Markdown）")
                chunks.extend(split_text(text, f"{file.name}#p{page + 1}"))
        elif file.suffix.lower() in (".md", ".markdown"):
            text = file.read_text(encoding="utf-8-sig").strip()
            if not text:
                raise ValueError(f"教材为空: {file.name}")
            chunks.extend(split_text(text, file.name))
        else:
            raise ValueError("教材仅支持 .md、.markdown、.pdf")
    budget = int(settings.get("max_chars", 24000))
    if budget < 1000:
        raise ValueError("materials.max_chars 至少为 1000")
    terms = set(re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2}", topic))
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
    return {"sources": sources, "selected_chunks": selected, "omitted_chunks": len(chunks) - len(selected), "context": context}


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
