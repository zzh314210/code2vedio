"""Explicit reasoning policy. Never retry by silently disabling reasoning.

The provider is the endpoint protocol owner, not the brand in a model name.
Hosted DeepSeek/Kimi through DashScope must select DashScope.
"""
import copy

PROVIDERS = {'compatible', 'openai', 'deepseek', 'moonshot', 'dashscope', 'anthropic', 'doubao', 'zhipu', 'minimax'}


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
    # Saved legacy switches must not override the explicit UI policy.
    extra = copy.deepcopy(settings.get('extra_body') or {})
    for key in ('enable_thinking', 'reasoning_effort', 'thinking', 'reasoning', 'thinking_budget', 'output_config'):
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
    elif provider == 'deepseek':
        extra.update(thinking={'type': 'enabled' if enabled else 'disabled'})
        if enabled: extra['reasoning_effort'] = effort
        else: effective = 'disabled'
    elif provider == 'openai':
        effective = native_openai
        if effective is not None:extra['reasoning_effort'] = effective
    elif provider == 'moonshot':
        extra['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        effective = 'model-default (官方仅提供思考开关)' if enabled else 'disabled'
    elif provider == 'doubao':
        extra['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        effective = 'high' if effort == 'max' else effort
        if enabled: extra['reasoning_effort'] = effective
        else: effective = 'disabled'
    elif provider == 'zhipu':
        extra['thinking'] = {'type': 'enabled' if enabled else 'disabled'}
        effective = 'enabled (供应商未提供强度参数)' if enabled else 'disabled'
    elif provider == 'minimax':
        if not enabled: raise ValueError('该供应商的推理模型不支持关闭思考')
        extra['reasoning_split'] = True
        effective = 'model-default (供应商未提供强度参数)'
    else:
        extra['enable_thinking'] = enabled
        if enabled: extra['reasoning_effort'] = effort
        else: effective = 'disabled'
    return extra, {'provider': provider, 'enabled': enabled, 'requested_effort': effort,
                   'effective_effort': effective or 'disabled (非推理模型)', 'body': extra}
