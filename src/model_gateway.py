import base64
import json
import mimetypes
import re
import time
import uuid
from types import SimpleNamespace
from pathlib import Path

from openai import OpenAI

from configuration import validate_model
from public_transport import public_client
from usage_meter import record_usage
from billing_client import call as billing_call, BillingError


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


class StructuredOutputError(ValueError):
    """Keep the last parsed candidate for narrowly scoped, validated repairs."""
    def __init__(self, message, candidate=None, validation_error=None):
        super().__init__(message)
        self.candidate = candidate
        self.validation_error = validation_error


class ModelGateway:
    def __init__(self, settings, role="text", on_request=None):
        validate_model(settings, role)
        self.settings = settings
        self.role = role
        self.primary_model = settings["model"]
        self.on_request = on_request
        self.client = OpenAI(
            api_key=settings["api_key"], base_url=settings["base_url"].rstrip("/"),
            timeout=float(settings.get("timeout", 180)), max_retries=0 if settings.get("billing_context") else int(settings.get("max_retries", 2)), **public_client(settings),
        )
        self.usage_recorded=False
        self.attempt_id=uuid.uuid4().hex
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def request(self, prompt, images=None, max_tokens=None):
        # Keep the endpoint, authentication and image payload identical across models.
        configured = [getattr(self, "primary_model", self.settings["model"]), *self.settings.get("fallback_models", [])]
        legacy = self.settings.get("quota_fallback_model")
        if legacy:
            configured.append(legacy)
        models = list(dict.fromkeys(configured))
        current = self.settings["model"]
        if current in models:
            start = models.index(current)
            models = models[start:] + models[:start]
        failures = []
        for index, model in enumerate(models):
            self.settings = {**self.settings, "model": model}
            self.attempt_id=uuid.uuid4().hex
            self.usage_recorded=False
            self.started_at=time.monotonic()
            self.first_token_ms=0
            try:
                return self._request(prompt, images, max_tokens)
            except BillingError:
                raise
            except Exception as failure:
                if not self.usage_recorded:
                    record_usage(self.settings,self.role,attempt_id=self.attempt_id,extra={'error_type':type(failure).__name__,'rejected':getattr(failure,'status_code',None) in (400,401,403,404,405,413,422,429),'duration_ms':int((time.monotonic()-self.started_at)*1000)})
                # Keep archived quota-only policies compatible; new fallback_models
                # explicitly authorize failover for every failed request and role.
                if not self.settings.get("fallback_models") and legacy:
                    detail = str(failure).lower()
                    exhausted = any(marker in detail for marker in ("insufficient_quota", "quota_exceeded", "quota exhausted", "quotaexceeded", "exceeded your current quota", "free tier quota", "arrearage"))
                    if self.role != "text" or not exhausted:
                        raise
                failures.append(failure)
                if index + 1 < len(models):
                    print(f"[{self.role}] {model} request failed; switching to {models[index + 1]}", flush=True)
        # Preserve the SDK exception type/status for the existing error handler.
        raise failures[-1]

    def meter(self, usage, response=None, error_type=""):
        if self.usage_recorded:return
        record_usage(self.settings,self.role,usage,getattr(response,'id',None),getattr(response,'model',None),self.attempt_id,extra={'error_type':error_type,'duration_ms':int((time.monotonic()-getattr(self,'started_at',time.monotonic()))*1000),'first_token_ms':getattr(self,'first_token_ms',0)})
        self.usage_recorded=True

    def _request(self, prompt, images=None, max_tokens=None):
        if self.on_request:
            stage=self.on_request(self.role, prompt, images or [])
            if stage:self.settings["usage_stage"]=stage
        billing_call(self.settings,'authorize',{'id':self.attempt_id,'model':self.settings['model'],'role':self.role,'max_output':int(max_tokens or self.settings.get('max_tokens',12000)),'input_bound':0 if images else len(prompt.encode('utf-8'))+1024,'stream':bool(self.settings.get('stream',False)),'stage':self.settings.get('usage_stage','')})
        limit = int(max_tokens or self.settings.get("max_tokens", 12000))
        extra = self.settings.get("extra_body", {})
        if self.settings["protocol"] == "responses":
            content = [{"type": "input_text", "text": prompt}]
            content.extend({"type": "input_image", "image_url": image_url(file)} for file in images or [])
            response = self.client.responses.create(
                model=self.settings["model"], input=[{"role": "user", "content": content}],
                max_output_tokens=limit, extra_body=extra, store=False,
            )
            self.meter(response.usage,response)
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
                extra_body=extra, stream=bool(self.settings.get("stream", False)),
                **({"stream_options":{"include_usage":True}} if self.settings.get("stream",False) else {}), **arguments,
            )
            if self.settings.get("stream", False):
                started = time.monotonic()
                last_progress = started
                fragments = []
                finish = None
                usage = None
                reasoning_chars = 0
                stream_response_id = None
                stream_model = None
                stream_error = ""
                try:
                    for chunk in response:
                        stream_response_id = getattr(chunk, "id", None) or stream_response_id
                        stream_model = getattr(chunk, "model", None) or stream_model
                        elapsed = time.monotonic() - started
                        if elapsed > float(self.settings.get("total_timeout", 600)):
                            raise TimeoutError("Model stream exceeded total_timeout")
                        if chunk.usage is not None:
                            usage = chunk.usage
                        for choice in chunk.choices:
                            if choice.delta.content:
                                if not self.first_token_ms:self.first_token_ms=int((time.monotonic()-self.started_at)*1000)
                                fragments.append(choice.delta.content)
                            reasoning_chars += len(getattr(choice.delta, "reasoning_content", None) or "")
                            if choice.finish_reason:
                                finish = choice.finish_reason
                        if time.monotonic() - last_progress >= 20:
                            print(f"[{self.role}] model stream: {elapsed:.0f}s, content={sum(map(len, fragments))} chars, reasoning={reasoning_chars} chars", flush=True)
                            last_progress = time.monotonic()
                except Exception as failure:
                    stream_error=type(failure).__name__
                    raise
                finally:
                    self.meter(usage, SimpleNamespace(id=stream_response_id, model=stream_model),stream_error or ("IncompleteOutput" if finish!="stop" else ""))
                    response.close()
                if finish != "stop":
                    raise ValueError(f"Model stream did not complete: {finish}")
                response = SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content="".join(fragments)))], usage=usage)
            self.meter(response.usage,response)
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
        previous = ""
        value = None
        validation_error = None
        for attempt in range(attempts):
            suffix = f"\n上次输出未通过校验：{error}。请重新返回完整合法 JSON，不要代码围栏。" if error else ""
            if previous:
                suffix += "\n上次输出（仅供定位和修正错误）：\n" + previous[:24000]
            text, unused_usage = self.request(prompt + suffix, images=images)
            value = None
            try:
                value = parse_json(text)
                if validator:
                    validator(value)
                return value
            except (ValueError, TypeError, KeyError, SyntaxError) as failure:
                error = str(failure)[:800]
                validation_error = failure
                previous = text
                # An unusable structured response is also a generation failure.
                # Honor the explicitly configured fallback order within the same retry budget.
                models = list(dict.fromkeys([self.primary_model, *self.settings.get("fallback_models", [])]))
                current = self.settings["model"]
                if attempt + 1 < attempts and current in models and models.index(current) + 1 < len(models):
                    following = models[models.index(current) + 1]
                    print(f"[{self.role}] {current} structured output invalid; switching to {following}", flush=True)
                    self.settings = {**self.settings, "model": following}
        raise StructuredOutputError(f"模型结构化输出在 {attempts} 次尝试后仍不合法: {error}", value, validation_error)
