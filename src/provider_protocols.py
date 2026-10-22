"""Explicit reasoning policy. Never retry by silently disabling reasoning.

The provider is the endpoint protocol owner, not the brand in a model name.
Hosted DeepSeek/Kimi through DashScope must select DashScope.
"""
import copy
import re

PROVIDERS = {'compatible', 'openai', 'deepseek', 'moonshot', 'dashscope', 'anthropic', 'doubao', 'zhipu', 'minimax'}


def domestic_chat(provider, model, enabled, effort):
    """Model-specific Chat Completions contracts, checked 2026-10-22.

    Sources and exceptions: deploy/PROVIDER_PROTOCOLS.md. These are request
    mappings, not claims that an upstream server echoes or honors a level.
    """
    hosted_moonshot = model.lower().startswith('kimi/')
    model = model.lower().rsplit('/', 1)[-1]
    if provider == 'deepseek':
        level = 'high' if effort == 'medium' else effort
        return {'thinking': {'type': 'enabled' if enabled else 'disabled'},
                **({'reasoning_effort': level} if enabled else {})}, level if enabled else 'disabled'
    if provider == 'moonshot':
        if model.startswith('kimi-k3'):
            if not enabled: raise ValueError('Kimi K3 官方接口始终思考，不支持关闭')
            level = 'high' if effort == 'medium' else effort
            # K3 explicitly forbids the older thinking switch.
            return {'reasoning_effort': level}, level
        if model.startswith('kimi-k2.7-code') and not enabled:
            raise ValueError('Kimi K2.7 Code 始终思考，不支持关闭')
        return {'thinking': {'type': 'enabled' if enabled else 'disabled'}}, 'model-default (此型号仅提供思考开关)' if enabled else 'disabled'
    if provider == 'zhipu':
        version = re.match(r'glm-(\d+)\.(\d+)', model)
        version = tuple(map(int, version.groups())) if version else (0, 0)
        if version == (5, 3) and not enabled:
            raise ValueError('GLM 5.3 此预设始终思考，不支持关闭')
        body = {'thinking': {'type': 'enabled' if enabled else 'disabled'}}
        if enabled and version in ((5, 2), (5, 3)):
            level = 'high' if effort == 'medium' or (version == (5, 2) and effort == 'low') else effort
            return {**body, 'reasoning_effort': level}, level
        return body, 'model-default (此型号未提供强度档位)' if enabled else 'disabled'
    if provider == 'minimax':
        if model.startswith('minimax-m3.1-flash'):
            if not enabled: raise ValueError('MiniMax M3.1 Flash 始终思考，不支持关闭')
            return {'reasoning_split': True, 'reasoning_effort': effort}, effort
        if model == 'minimax-m3':
            return {'thinking': {'type': 'adaptive' if enabled else 'disabled'}, 'reasoning_split': True}, 'adaptive (此型号无强度档位)' if enabled else 'disabled'
        if not enabled: raise ValueError('该 MiniMax 型号不支持关闭思考')
        return {'reasoning_split': True}, 'model-default (此型号未提供强度档位)'
    # DashScope is not one universal protocol for all hosted model families.
    body = {'enable_thinking': enabled}
    if model.startswith('qwen3.8'):
        if model.startswith('qwen3.8-2.4t') and not enabled:
            raise ValueError('此 Qwen 3.8 型号只支持思考模式')
        level = 'xhigh' if effort in ('max', 'high') else effort
    elif model.startswith(('glm-5.3', 'kimi-k3')):
        if model.startswith('glm-5.3') and not enabled:
            raise ValueError('托管 GLM 5.3 始终思考，不支持关闭')
        if model.startswith('kimi-k3') and hosted_moonshot:
            if not enabled: raise ValueError('月之暗面直供 Kimi K3 始终思考，不支持关闭')
            level = 'max'
        else: level = 'high' if effort == 'medium' else effort
    elif model.startswith('deepseek-v4'):
        level = 'high' if effort == 'medium' or (model == 'deepseek-v4-pro' and effort == 'low') else effort
    elif model.startswith('glm-5'):
        level = 'high' if effort in ('low', 'medium') else effort
    elif model.startswith('minimax-m3'):
        if model.startswith('minimax-m3.1-flash'):
            if not enabled: raise ValueError('托管 MiniMax M3.1 Flash 始终思考，不支持关闭')
            return {'thinking': {'type': 'adaptive'}, 'reasoning_effort': effort}, effort
        return {'thinking': {'type': 'adaptive' if enabled else 'disabled'}}, 'adaptive (此型号无强度档位)' if enabled else 'disabled'
    elif model.startswith(('qwen3', 'qwen-plus', 'qwen-flash', 'glm-4', 'kimi-k2', 'minimax-m2')):
        if model.startswith(('kimi-k2.7-code', 'minimax-m2')) and not enabled:
            raise ValueError('此托管型号只支持思考模式')
        return body, 'model-default (此型号无已核实强度档位)' if enabled else 'disabled'
    else:
        # Keep explicit pass-through for private aliases, but never call it
        # verified. Unknown aliases require the endpoint owner's contract.
        return {**body, **({'reasoning_effort': effort} if enabled else {})}, effort+' (兼容透传，型号未核实)' if enabled else 'disabled'
    return {**body, **({'reasoning_effort': level} if enabled else {})}, level if enabled else 'disabled'


def openai_effort(model, enabled, effort):
    """Map the product's Max choice to known model capabilities.

    Unknown future names keep the requested value and let the endpoint give a
    clear error; no paid retry silently lowers a requested capability.
    """
    model=model.lower()
    legacy=any(model.startswith(p) for p in ('o1','o3','o4-mini')) or model=='gpt-5' or model.startswith(('gpt-5-','gpt-5.1'))
    if model.startswith(('gpt-4','gpt-3')):
        if enabled:raise ValueError('该 OpenAI 型号不支持深度思考，请选择推理模型或关闭思考')
        return None
    if not enabled:
        if legacy and not model.startswith('gpt-5.1'):raise ValueError('该 OpenAI 推理型号不支持关闭思考')
        return 'none'
    if effort!='max':return effort
    if legacy:return 'high'
    if model.startswith(('gpt-5.2','gpt-5.3','gpt-5.4','gpt-5.5')):return 'xhigh'
    return 'max'


def reasoning_body(settings, limit):
    provider = settings.get('provider') or 'compatible'
    if provider not in PROVIDERS:
        raise ValueError('未知模型供应商')
    enabled = settings.get('thinking_enabled', True)
    effort = settings.get('reasoning_effort') or 'max'
    if not isinstance(enabled, bool) or effort not in ('low', 'medium', 'high', 'max'):
        raise ValueError('思考开关或强度无效')
    protocol = settings.get('protocol', 'chat_completions')
    if provider in ('deepseek','moonshot','zhipu','minimax','doubao','dashscope') and protocol != 'chat_completions':
        raise ValueError('此供应商预设按 Chat Completions 协议适配；请使用预设协议')
    # Saved legacy switches must not override the explicit UI policy.
    extra = copy.deepcopy(settings.get('extra_body') or {})
    for key in ('enable_thinking', 'reasoning_effort', 'thinking', 'reasoning', 'thinking_budget', 'output_config', 'reasoning_split'):
        extra.pop(key, None)
    effective = effort
    native_openai = openai_effort(settings['model'],enabled,effort) if provider=='openai' else None
    if provider == 'anthropic':
        if protocol != 'anthropic':
            raise ValueError('Claude 官方供应商需选择 Messages 协议；中转服务请选择其兼容协议')
        if not enabled:
            extra['thinking'] = {'type': 'disabled'}
            effective = 'disabled'
        elif any(x in settings['model'].lower() for x in ('opus-4-6', 'opus-4-7', 'sonnet-4-6')):
            extra['thinking'] = {'type': 'adaptive'}
            effective = effort if 'opus' in settings['model'].lower() else ('high' if effort == 'max' else effort)
            extra['output_config'] = {'effort': effective}
        else:
            if limit < 2048:
                raise ValueError('Claude 扩展思考最大输出至少需 2048 token')
            budget = min({'low': 2048, 'medium': 4096, 'high': 8192, 'max': 32768}[effort], limit - 1024)
            extra['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
            effective = f'budget:{budget}'
    elif protocol == 'responses':
        effective = native_openai if provider=='openai' else effort if enabled else 'none'
        if effective is not None:extra['reasoning'] = {'effort': effective}
    elif provider in ('deepseek', 'moonshot', 'zhipu', 'minimax', 'dashscope'):
        body, effective = domestic_chat(provider, settings['model'], enabled, effort)
        extra.update(body)
    elif provider == 'openai':
        effective = native_openai
        if effective is not None:extra['reasoning_effort'] = effective
    elif provider == 'doubao':
        extra['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        effective = 'high' if effort == 'max' else effort
        if enabled: extra['reasoning_effort'] = effective
        else: effective = 'disabled'
    else:
        extra['enable_thinking'] = enabled
        if enabled: extra['reasoning_effort'] = effort
        else: effective = 'disabled'
    return extra, {'provider': provider, 'enabled': enabled, 'requested_effort': effort,
                   'effective_effort': effective or 'disabled (非推理模型)', 'body': extra}
