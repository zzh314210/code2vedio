"""Check the deployed HTTPS Studio without keys, uploads or paid generation."""
import base64
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
credentials = dict(line.split('=', 1) for line in Path('/data/code2vedio-access.txt').read_text().splitlines())
base = credentials['URL']
encoded = base64.b64encode((credentials['USERNAME'] + ':' + credentials['PASSWORD']).encode()).decode()

def request(path, authenticated=True, method='GET', origin=None):
    headers = {'User-Agent': 'Mozilla/5.0'}
    if authenticated:
        headers['Authorization'] = 'Basic ' + encoded
    if origin:
        headers['Origin'] = origin
    data = None
    if method == 'POST':
        headers['Content-Type'] = 'application/json'
        data = b'{}'
    req = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read()
    except HTTPError as response:
        return response.code, response.read()

for path in ('/', '/api/config', '/api/jobs'):
    assert request(path, authenticated=False)[0] == 401, path
    status, _ = request(path)
    assert status == 200, (path, status)
assert request('/api/config', method='POST', origin=base)[0] == 200
assert request('/api/config', method='POST', origin='https://foreign.example')[0] == 403
styles = json.loads(request('/api/styles')[1])
assert len(styles) == 3

artifacts = ROOT / '.tmp/deployment-check'
artifacts.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(http_credentials={'username': credentials['USERNAME'], 'password': credentials['PASSWORD']}, viewport={'width': 1440, 'height': 1050})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    response = page.goto(base, wait_until='networkidle', timeout=60000)
    assert response.status == 200
    assert page.get_by_role('button', name='生成视频', exact=True).is_disabled()
    page.get_by_role('button', name='试试复利讲解').click()
    assert page.get_by_role('button', name='生成视频', exact=True).is_enabled()
    page.locator('.theme-card').filter(has_text='手绘课堂').click()
    assert page.locator('.theme-card').filter(has_text='手绘课堂').get_attribute('aria-pressed') == 'true'
    page.screenshot(path=str(artifacts / 'desktop.png'), full_page=True)
    page.get_by_role('button', name='配置', exact=True).click()
    assert page.get_by_role('dialog').is_visible()
    assert page.locator('#text-key').get_attribute('type') == 'password'
    with page.expect_response(lambda r: r.url.endswith('/api/config') and r.request.method == 'POST') as saved:
        page.get_by_role('button', name='保存配置').click()
    assert saved.value.status == 200, saved.value.text()
    page.get_by_role('button', name='配置已保存').wait_for()
    page.get_by_role('button', name='返回创作').click()
    for width, height in ((390, 844), (768, 1024)):
        page.set_viewport_size({'width': width, 'height': height})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(artifacts / f'responsive-{width}.png'), full_page=True)
    assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
    assert not errors, errors
    browser.close()
print('PASS: public HTTPS, authentication on page/API, 3 styles, allowed/foreign origins, React interactions, real domain config save, responsive layout and empty browser storage; no paid generation.')
