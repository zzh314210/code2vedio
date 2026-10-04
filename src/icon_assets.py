import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from defusedxml.ElementTree import fromstring

from configuration import ROOT, validate_endpoint
from media import run_command


def mcp_result(message):
    if "error" in message:
        raise ValueError(f"MCP error: {message['error']}")
    result = message.get("result", {})
    if result.get("isError"):
        raise ValueError("MCP 工具调用失败")
    if "structuredContent" in result:
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except json.JSONDecodeError:
                if "<svg" in item["text"]:
                    return {"svg": item["text"]}
    return result


class MCPIcons:
    def __init__(self, url, timeout=20):
        validate_endpoint(url)
        self.url = url
        self.client = httpx.Client(timeout=timeout, headers={"Accept": "application/json, text/event-stream"})
        self.identifier = 0
        response = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Code2Video", "version": "2026.10"}})
        self.version = response.get("protocolVersion", "2025-06-18")
        self.client.headers["MCP-Protocol-Version"] = self.version
        self.client.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"})

    def rpc(self, method, parameters):
        self.identifier += 1
        response = self.client.post(self.url, json={"jsonrpc": "2.0", "id": self.identifier, "method": method, "params": parameters})
        response.raise_for_status()
        if "mcp-session-id" in response.headers:
            self.client.headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    message = json.loads(line[5:].strip())
                    if message.get("id") == self.identifier:
                        return mcp_result(message)
            raise ValueError("MCP 流没有返回匹配的请求 ID")
        return mcp_result(response.json())

    def call(self, name, arguments):
        return self.rpc("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        self.client.close()


def safe_svg(svg, color):
    if not isinstance(svg, str) or len(svg.encode("utf-8")) > 512000:
        raise ValueError("SVG 数据为空或超过 500KB")
    if not re.fullmatch(r"#[A-Fa-f0-9]{6}", color):
        raise ValueError("assets.color 必须是六位十六进制颜色")
    root = fromstring(svg)
    if root.tag.split("}")[-1] != "svg":
        raise ValueError("素材不是 SVG")
    styles = {}
    for parent in root.iter():
        for element in list(parent):
            if element.tag.split("}")[-1] == "style":
                stylesheet = element.text or ""
                if re.search(r"url\(|@|javascript:|expression\s*\(", stylesheet, re.I):
                    raise ValueError("SVG 样式包含外部资源")
                rules = re.findall(r"\.([\w-]+)\s*\{([^{}]*)\}", stylesheet)
                for class_name, declarations in rules:
                    styles[class_name] = dict(item.split(":", 1) for item in declarations.split(";") if ":" in item)
                parent.remove(element)
    allowed = {"svg", "g", "defs", "path", "circle", "rect", "line", "polygon", "polyline", "ellipse", "clipPath", "linearGradient", "radialGradient", "stop", "symbol", "use", "title", "desc"}
    for element in root.iter():
        if element.tag.split("}")[-1] not in allowed:
            raise ValueError(f"SVG 包含不允许的元素: {element.tag}")
        for class_name in element.attrib.get("class", "").split():
            for property_name, value in styles.get(class_name, {}).items():
                property_name = property_name.strip()
                if property_name in ("fill", "fill-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity", "fill-opacity", "stroke-opacity"):
                    element.attrib[property_name] = value.strip()
        for key, value in list(element.attrib.items()):
            name = key.split("}")[-1].lower()
            if name.startswith("on") or name in ("src", "href") and not value.startswith("#"):
                raise ValueError("SVG 包含外部资源或事件")
            if re.search(r"url\(\s*['\"]?(?!#)|javascript:|expression\s*\(|@import", value, re.I):
                raise ValueError("SVG 包含外部引用或可执行样式")
            element.attrib[key] = value.replace("currentColor", color)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="unicode")


def download_svg(url):
    validate_endpoint(url)
    host = urlsplit(url).hostname or ""
    allowed = ("infyicon.com", "iconify.design", "lucide.dev", "githubusercontent.com", "unpkg.com", "jsdelivr.net", "storyset.com", "doodleipsum.com", "iconoodle.com", "ira.design")
    if not any(host == domain or host.endswith("." + domain) for domain in allowed):
        raise ValueError(f"图形下载域名未在允许名单: {host}")
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks, total = [], 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > 512000:
                    raise ValueError("下载的 SVG 超过 500KB")
                chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


class AssetManager:
    def __init__(self, settings, output):
        self.settings = settings
        self.output = Path(output)
        self.cache = self.output / "assets"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.records = []
        self.errors = []

    def enabled_sources(self):
        return [(name, options) for name, options in self.settings.get("sources", {}).items() if options.get("enabled")]

    def from_source(self, name, options, keyword):
        color = self.settings.get("color", "#58C4DD")
        if name in ("iconvaultkit", "infyicon"):
            client = MCPIcons(options["url"], self.settings.get("timeout", 20))
            try:
                arguments = {"query": keyword, "limit": 1}
                if name == "iconvaultkit" and options.get("collection"):
                    arguments["collection"] = options["collection"]
                if name == "infyicon":
                    arguments["style"] = options.get("style", "outline")
                results = client.call("search_icons", arguments).get("icons", [])
                if not results:
                    if name == "iconvaultkit" and options.get("collection") and re.fullmatch(r"[a-z0-9-]+", keyword):
                        results = [options["collection"] + ":" + keyword]
                    else:
                        return []
                if name == "iconvaultkit":
                    collection, icon = results[0].split(":", 1)
                    data = client.call("get_icon_svg", {"collection": collection, "name": icon, "color": color})
                    return [{"id": results[0], "svg": data["svg"], "credit": f"{collection} icons via IconVaultKit", "license": "请核对该图标集的独立许可", "source": name}]
                icon = results[0]
                data = client.call("get_icon_svg", {"id": icon["id"]})
                svg = data.get("svg") or download_svg(data.get("svg_url") or icon["svg_url"])
                return [{"id": icon["id"], "svg": svg, "credit": "Icons: infyicon.com", "license": "https://infyicon.com/license (需署名)", "source": name}]
            finally:
                client.close()
        if name == "graphics_api_remotion":
            node = shutil.which("node")
            if not node or not (ROOT / "tools/graphics/node_modules/graphics-api-remotion").is_dir():
                raise ValueError("graphics-api-remotion 未安装；运行 scripts/setup_windows.ps1 -WithGraphics")
            request = {"keyword": keyword, "providers": options.get("providers", ["lucide"]), "style": options.get("style", "regular"), "color": color, "limit": 1}
            response = run_command([node, str(ROOT / "tools/graphics/query.mjs"), json.dumps(request)], timeout=90)
            graphics = json.loads(response)
            records = []
            for item in graphics:
                source = item["source"]
                records.append({"id": hashlib.sha256(item["url"].encode()).hexdigest()[:16], "svg": item.get("svg") or download_svg(item["url"]), "credit": {"storyset": "Illustrations: Storyset by Freepik", "iconoodle": "Graphics: Iconoodle", "doodle-ipsum": "Graphics: Doodle Ipsum"}.get(source, f"{source} icons"), "license": "依实际数据源核对许可（npm MIT 不等于素材许可）", "source": name + "/" + source})
            return records
        raise ValueError(f"未知图标源: {name}")

    def fetch(self, keyword):
        output = []
        for name, options in self.enabled_sources():
            digest = hashlib.sha256(json.dumps({"source": name, "options": options, "keyword": keyword, "color": self.settings.get("color")}, sort_keys=True).encode()).hexdigest()[:20]
            metadata = self.cache / (digest + ".json")
            try:
                if metadata.exists():
                    records = json.loads(metadata.read_text(encoding="utf-8"))
                    if any(not Path(record["path"]).is_file() for record in records):
                        raise ValueError("图标缓存文件缺失")
                else:
                    records = self.from_source(name, options, keyword)
                    for index, record in enumerate(records):
                        destination = self.cache / f"{digest}_{index}.svg"
                        destination.write_text(safe_svg(record.pop("svg"), self.settings.get("color", "#58C4DD")), encoding="utf-8")
                        record.update({"path": str(destination), "keyword": keyword, "key": f"asset_{digest}_{index}"})
                    metadata.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                output.extend(records)
                if records and self.settings.get("strategy", "first_success") == "first_success":
                    break
            except Exception as error:
                self.errors.append({"source": name, "keyword": keyword, "error": str(error)[:1000]})
                if self.settings.get("strict"):
                    raise
        self.records.extend(output)
        return output

    def check(self):
        result = []
        for name, options in self.enabled_sources():
            try:
                found = self.from_source(name, options, "book")
                for record in found:
                    safe_svg(record["svg"], self.settings.get("color", "#58C4DD"))
                result.append({"source": name, "ok": bool(found), "count": len(found)})
            except Exception as error:
                result.append({"source": name, "ok": False, "error": str(error)[:1000]})
        return result

    def save_attribution(self):
        (self.output / "assets.json").write_text(json.dumps({"assets": self.records, "errors": self.errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        credits = sorted({record["credit"] + " — " + record["license"] for record in self.records})
        (self.output / "ATTRIBUTION.md").write_text("# 素材出处与许可\n\n" + "\n".join("- " + line for line in credits), encoding="utf-8")
