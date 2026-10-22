"""Truncated reasoning/answers must be billed once and never reach rendering."""
import json
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from configuration import resolve_config
from model_gateway import ModelGateway, OutputLimitError

with tempfile.TemporaryDirectory() as temp:
    for streaming, finish, answer in [(True, 'length', ''), (True, 'length', '{"partial":'), (False, 'length', ''), (True, 'stop', '{"ok":true}')]:
        usage_file = Path(temp) / f'{streaming}-{finish}-{len(answer)}.jsonl'
        settings = resolve_config({'text': {
            'provider': 'dashscope', 'model': 'deepseek-v4.1-flash-1017',
            'protocol': 'chat_completions', 'api_key': 'fixture-key',
            'base_url': 'https://example.com/v1', 'stream': streaming,
            'max_tokens': 65536, 'max_retries': 0, 'usage_file': str(usage_file),
        }})['text']
        calls = []
        def respond(request):
            body = json.loads(request.content)
            calls.append(body)
            assert body.get('max_tokens', body.get('max_completion_tokens')) == 65536
            assert body['reasoning_effort'] == 'max' and body['enable_thinking'] is True
            usage = {'prompt_tokens': 100, 'completion_tokens': 65536, 'total_tokens': 65636,
                     'completion_tokens_details': {'reasoning_tokens': 65536 if not answer else 64000}}
            if streaming:
                chunks = [
                    {'id': 'stream', 'model': body['model'], 'choices': [{'index': 0, 'delta': {'reasoning_content': 'private-thought'}, 'finish_reason': None}]},
                    {'id': 'stream', 'model': body['model'], 'choices': [{'index': 0, 'delta': {'content': answer}, 'finish_reason': finish}]},
                    {'id': 'stream', 'model': body['model'], 'choices': [], 'usage': usage},
                ]
                data = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
                return httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=data)
            return httpx.Response(200, json={'id': 'buffered', 'model': body['model'], 'choices': [{'index': 0, 'finish_reason': finish, 'message': {'role': 'assistant', 'content': answer}}], 'usage': usage})
        gateway = ModelGateway(settings)
        gateway.client._client.close()
        gateway.client._client = httpx.Client(transport=httpx.MockTransport(respond))
        try:
            result = gateway.json('Generate code')
            assert finish == 'stop' and result == {'ok': True}
        except OutputLimitError as error:
            assert finish == 'length'
            assert '65,536' in str(error) and '思考与正文' in str(error)
            assert ('没有返回正文' in str(error)) == (not answer)
        finally:
            gateway.client.close()
        assert len(calls) == 1, 'do not repeat a truncated call with the same budget'
        events = [json.loads(line) for line in usage_file.read_text().splitlines()]
        assert len(events) == 1 and events[0]['output_tokens'] == 65536
        assert events[0]['error_type'] == ('IncompleteOutput' if finish == 'length' else '')
        assert 'private-thought' not in usage_file.read_text()

print('PASS: 65,536 output budget and Max thinking sent, streaming/buffered truncation rejected, partial JSON not consumed, one metered call, Chinese errors, no private thoughts stored')
