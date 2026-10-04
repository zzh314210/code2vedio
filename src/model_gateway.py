import base64
import json
import mimetypes
import re
from pathlib import Path

from openai import OpenAI

from configuration import validate_model


def parse_json(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def image_url(filename):
    file = Path(filename)
    mime = mimetypes.guess_type(file.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(file.read_bytes()).decode("ascii")


class ModelGateway:
    def __init__(self, settings, role="text", on_request=None):
        validate_model(settings, role)
        self.settings = settings
        self.role = role
        self.on_request = on_request
        self.client = OpenAI(
            api_key=settings["api_key"], base_url=settings["base_url"].rstrip("/"),
            timeout=float(settings.get("timeout", 180)), max_retries=int(settings.get("max_retries", 2)),
        )
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def request(self, prompt, images=None, max_tokens=None):
        if self.on_request:
            self.on_request(self.role, prompt, images or [])
        limit = int(max_tokens or self.settings.get("max_tokens", 12000))
        extra = self.settings.get("extra_body", {})
        if self.settings["protocol"] == "responses":
            content = [{"type": "input_text", "text": prompt}]
            content.extend({"type": "input_image", "image_url": image_url(file)} for file in images or [])
            response = self.client.responses.create(
                model=self.settings["model"], input=[{"role": "user", "content": content}],
                max_output_tokens=limit, extra_body=extra, store=False,
            )
            if response.status == "incomplete":
                raise ValueError("Responses 返回 incomplete；请提高 text.max_tokens 或减小课程长度")
            text = response.output_text
            usage = response.usage
            incoming = getattr(usage, "input_tokens", 0) or 0
            outgoing = getattr(usage, "output_tokens", 0) or 0
        else:
            content = [{"type": "text", "text": prompt}]
            content.extend({"type": "image_url", "image_url": {"url": image_url(file)}} for file in images or [])
            arguments = {self.settings.get("token_parameter", "max_completion_tokens"): limit}
            response = self.client.chat.completions.create(
                model=self.settings["model"], messages=[{"role": "user", "content": content}],
                extra_body=extra, **arguments,
            )
            if not response.choices or response.choices[0].finish_reason in ("length", "content_filter"):
                raise ValueError("Chat Completions 输出被截断/过滤；请提高 max_tokens 或检查输入")
            text = response.choices[0].message.content
            usage = response.usage
            incoming = getattr(usage, "prompt_tokens", 0) or 0
            outgoing = getattr(usage, "completion_tokens", 0) or 0
        if not isinstance(text, str) or not text.strip():
            raise ValueError("模型没有返回文本，可能拒答或接口格式不兼容")
        current = {"prompt_tokens": incoming, "completion_tokens": outgoing, "total_tokens": incoming + outgoing}
        for key, value in current.items():
            self.usage[key] += value
        return text.strip(), current

    def json(self, prompt, validator=None, attempts=3, images=None):
        error = ""
        for attempt in range(attempts):
            suffix = f"\n上次输出未通过校验：{error}。请重新返回完整合法 JSON，不要代码围栏。" if error else ""
            text, unused_usage = self.request(prompt + suffix, images=images)
            try:
                value = parse_json(text)
                if validator:
                    validator(value)
                return value
            except (ValueError, TypeError, KeyError, SyntaxError) as failure:
                error = str(failure)[:800]
        raise ValueError(f"模型结构化输出在 {attempts} 次尝试后仍不合法: {error}")
