"""Provider-neutral personal model configuration; no host credentials are inherited."""
import copy
from urllib.parse import urlsplit
from pydantic import BaseModel, Field
from typing import Literal
from configuration import DEFAULTS, validate_endpoint
from teaching_research import public_url


class ModelConfig(BaseModel):
    base_url: str = Field(default='', max_length=500)
    model: str = Field(default='', max_length=150)
    api_key: str = Field(default='', max_length=2048)
    clear_key: bool = False
    protocol: Literal['responses', 'chat_completions'] = 'chat_completions'
    fallback_models: list[str] = Field(default_factory=list, max_length=8)


class SpeechConfig(BaseModel):
    provider: Literal['edge', 'openai'] = 'edge'
    base_url: str = Field(default='', max_length=500)
    model: str = Field(default='', max_length=150)
    api_key: str = Field(default='', max_length=2048)
    clear_key: bool = False
    voice: str = Field(default='zh-CN-XiaoxiaoNeural', min_length=1, max_length=100)


class PersonalConfig(BaseModel):
    text: ModelConfig = Field(default_factory=ModelConfig)
    vision: ModelConfig = Field(default_factory=ModelConfig)
    vision_inherit: bool = False
    tts: SpeechConfig = Field(default_factory=SpeechConfig)


def validate_public_endpoint(url):
    validate_endpoint(url)
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.port not in (None, 443):
        raise ValueError('模型接口需使用公开 HTTPS 地址（443端口）。')
    try:
        public_url(url)
    except Exception as error:
        raise ValueError('接口地址无法解析或指向内网，请填写服务商提供的公开地址。') from error


def saved_config(data, previous):
    value = data.model_dump()
    for role in ('text', 'vision', 'tts'):
        item = value[role]
        item['base_url'] = item['base_url'].strip().rstrip('/')
        item['model'] = item['model'].strip()
        if item['base_url']:
            validate_public_endpoint(item['base_url'])
        if any(c in item['model'] for c in '\r\n'):
            raise ValueError('模型名称不能包含换行。')
        if role != 'tts':
            if any(not model.strip() or len(model) > 150 for model in item['fallback_models']):
                raise ValueError('备用模型名称需为1至150位。')
            item['fallback_models'] = list(dict.fromkeys(m.strip() for m in item['fallback_models']))
        old = previous.get(role, {})
        key = item['api_key'].strip()
        # A changed endpoint must never receive a key saved for a different service.
        item['api_key'] = '' if item.pop('clear_key') else key or (old.get('api_key', '') if old.get('base_url', '') == item['base_url'] else '')
    return value


def visible_config(value):
    result = copy.deepcopy(value or PersonalConfig().model_dump())
    for role in ('text', 'vision', 'tts'):
        item = result[role]
        item['key_configured'] = bool(item.pop('api_key', ''))
        item.pop('clear_key', None)
    text_ready = all(value.get('text', {}).get(k) for k in ('base_url', 'model', 'api_key'))
    vision_ready = text_ready if result.get('vision_inherit', True) else all(value.get('vision', {}).get(k) for k in ('base_url', 'model', 'api_key'))
    tts = value.get('tts', {})
    speech_ready = tts.get('provider', 'edge') == 'edge' or all(tts.get(k) for k in ('base_url', 'model', 'api_key', 'voice'))
    return {**result, 'text_ready': bool(text_ready), 'vision_ready': bool(vision_ready), 'speech_ready': bool(speech_ready)}


def runtime_config(base, personal, library):
    result = copy.deepcopy(base)
    # Only infrastructure/video settings come from the deployment; model channels are personal.
    for role in ('text', 'vision', 'tts'):
        result[role] = copy.deepcopy(DEFAULTS[role])
    text = personal.get('text', {})
    result['text'].update(text)
    result['text']['api_key'] = text.get('api_key', '')
    result['text']['token_parameter'] = 'max_tokens'
    result['text']['public_endpoint_only'] = True
    result['text']['max_retries'] = 0
    if personal.get('vision_inherit', True):
        result['vision'] = copy.deepcopy(result['text'])
    else:
        result['vision'] = {**copy.deepcopy(result['text']), **personal.get('vision', {}), 'api_key': personal.get('vision', {}).get('api_key', '')}
    result['vision']['public_endpoint_only'] = True
    result['vision'].update(enabled=True, inherit_text=False, frames=12, rounds=2, require_pass=True)
    result['tts'].update(personal.get('tts', {}))
    result['tts']['public_endpoint_only'] = True
    result['teaching_research'] = {**result.get('teaching_research', {}), 'library': str(library), 'source_ids': [], 'reference_urls': []}
    return result
