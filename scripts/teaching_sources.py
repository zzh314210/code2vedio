"""Standalone teaching corpus CLI: search, ingest URLs in bulk, query indexed content."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from configuration import load_config
from teaching_library import TeachingSources

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=["search", "ingest", "batch", "local", "stats"])
    p.add_argument("value", nargs="?", default="")
    p.add_argument("--platform", default="web", choices=["web", "bilibili", "zhihu", "library"])
    p.add_argument("--config")
    a = p.parse_args()
    service = TeachingSources(load_config(a.config).get("teaching_research", {}))
    if a.operation == "stats": result = service.library.stats()
    elif a.operation == "search": result = service.search(a.value, a.platform)
    elif a.operation == "ingest": result = service.ingest(a.value)
    elif a.operation == "local": result = service.ingest_local(a.value)
    else:
        result = []
        for url in Path(a.value).read_text(encoding="utf-8-sig").splitlines():
            if not url.strip() or url.lstrip().startswith("#"): continue
            try:
                item = service.ingest(url.strip())
                result.append({"url": url, "id": item["id"], "status": "indexed"})
            except Exception as e: result.append({"url": url, "status": "failed", "error": str(e)})
    print(json.dumps(result, ensure_ascii=False, indent=2))
