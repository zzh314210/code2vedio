"""Free Wikimedia search and full article bodies, with bounded fixed-host requests."""
import json
import time
from urllib.parse import quote

import requests

API = 'https://zh.wikipedia.org/w/api.php'
HEADERS = {'User-Agent': 'PelicanVideoStudio/1.0 (educational references; https://vedio.myaihub.asia)'}


def get_json(url, params, timeout=5):
    start = time.monotonic()
    # Both callers use fixed Wikimedia hosts. Do not follow upstream redirects.
    with requests.get(url, params=params, headers=HEADERS, timeout=(min(3, timeout), timeout), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 2_000_000 or time.monotonic() - start > timeout + 3:
                raise TimeoutError('百科正文读取超过限制')
            chunks.append(chunk)
        value = json.loads(b''.join(chunks))
        if not isinstance(value, dict) or value.get('error'):
            raise ValueError('百科接口未返回有效结果')
        return value


def search(query, limit=6):
    limit = min(max(int(limit), 1), 12)
    try:
        value = get_json(API, {'action': 'query', 'list': 'search', 'srsearch': query, 'srlimit': limit, 'format': 'json', 'utf8': 1})
        hits = value['query']['search']
    except (requests.RequestException, ValueError, KeyError, TimeoutError):
        # Wikimedia's separate REST route survives Action API failures/limits.
        value = get_json('https://zh.wikipedia.org/w/rest.php/v1/search/page', {'q': query, 'limit': limit})
        hits = [{'title': hit['title'], 'pageid': hit['id']} for hit in value['pages']]
    return [{'title': hit['title'], 'pageid': hit['pageid'], 'url': 'https://zh.wikipedia.org/wiki/' + quote(hit['title']), 'kind': 'article'} for hit in hits]


def article(item):
    # TextExtracts permits only one full article per request; exintro is not used.
    value = get_json(API, {'action': 'query', 'pageids': int(item['pageid']), 'prop': 'extracts', 'explaintext': 1, 'format': 'json', 'formatversion': 2, 'utf8': 1})
    page = value['query']['pages'][0]
    text = page.get('extract', '').strip()
    if page.get('missing') or len(text) < 200:
        raise ValueError('百科条目没有足够正文')
    return {'url': item['url'], 'title': page['title'], 'text': text[:48000], 'kind': 'article', 'backend': 'wikimedia-textextracts', 'truncated': len(text) > 48000}
