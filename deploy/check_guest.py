"""Real browser acceptance of guest entry, deferred login and draft preservation.

Uses an existing administrator session only to verify return navigation. Never
submits a job or changes model settings, and leaves no test credentials active.
"""
from browser_helpers import dismiss_guide, assert_safe_storage
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('C2V_CHECK_URL', 'https://vedio.myaihub.asia').rstrip('/')
ARTIFACTS = ROOT / '.tmp/guest-check'
ARTIFACTS.mkdir(parents=True, exist_ok=True)
CREDENTIALS = dict(line.split('=', 1) for line in (ROOT / 'private/admin-access.txt').read_text().splitlines())
PROMPT = '制作90秒的原创考公题目讲解，先给出题干，再用手绘图示解释净消耗，最后验证答案。'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1050})
    page = context.new_page()
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append((request.method, urlsplit(request.url).path)))

    def login():
        page.locator('[name=username]').fill(CREDENTIALS['USERNAME'])
        page.locator('[name=password]').fill(CREDENTIALS['PASSWORD'])
        page.get_by_role('button', name='登录工作空间', exact=True).click()
        expect(page.locator('.auth-page')).to_have_count(0)
        expect(page.get_by_role('button', name='退出登录', exact=True)).to_be_visible()
        dismiss_guide(page)

    def back():
        page.get_by_role('button', name='返回创作面板', exact=True).click()
        expect(page.get_by_role('heading', name='让想法，成为画面。')).to_be_visible()

    def draft():
        expect(page.locator('#prompt')).to_have_value(PROMPT)
        expect(page.locator('#duration')).to_have_value('90')
        expect(page.get_by_role('button', name='9:16', exact=True)).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('.input-panel .theme-card').filter(has_text='手绘课堂')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#source-query')).to_have_value('牛吃草 净消耗')
        expect(page.locator('#reference-urls')).to_have_value('https://example.org/lesson')
        expect(page.get_by_role('checkbox', name='免审核，自动完成')).to_be_checked()

    try:
        response = page.goto(BASE, wait_until='networkidle')
        assert response.status == 200 and 'www-authenticate' not in response.headers
        expect(page.get_by_role('heading', name='让想法，成为画面。')).to_be_visible()
        expect(page.locator('[name=username]')).to_have_count(0)
        expect(page.locator('.input-panel').get_by_role('heading', name='视频创作', exact=True)).to_be_visible()
        expect(page.locator('.preview-panel').get_by_role('heading', name='画面预览', exact=True)).to_be_visible()
        expect(page.locator('.panel-number')).to_have_count(0)
        expect(page.locator('.input-panel .themes-section .theme-card')).to_have_count(3)
        expect(page.locator('.preview-panel .theme-card, .preview-style-switch')).to_have_count(0)
        expect(page.locator('.creation-steps [aria-current=step]')).to_have_count(1)
        expect(page.locator('.creation-steps [aria-current=step]')).to_contain_text('描述想法')
        assert [path for method, path in requests if path.startswith('/api/')] == ['/api/auth/me'], requests
        for path in ['/api/jobs', '/api/config', '/api/wallet', '/api/sources', '/api/voices', '/api/api-keys']:
            assert context.request.get(BASE + path).status == 401, path

        page.locator('#prompt').fill(PROMPT)
        page.locator('#duration').select_option('90')
        page.get_by_role('button', name='9:16', exact=True).click()
        page.locator('.input-panel .theme-card').filter(has_text='手绘课堂').click()
        page.get_by_role('checkbox', name='免审核，自动完成').check()
        page.locator('#source-query').fill('牛吃草 净消耗')
        page.locator('#reference-urls').fill('https://example.org/lesson')
        expect(page.locator('.creation-summary')).to_contain_text('90 秒')
        expect(page.locator('.creation-summary')).to_contain_text('竖屏 9:16')
        draft()
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ARTIFACTS / 'guest-desktop.png'), full_page=True)

        page.get_by_role('button', name='生成视频', exact=True).click()
        expect(page.get_by_role('heading', name='欢迎回来')).to_be_visible()
        expect(page.locator('.auth-card')).to_contain_text('已填写的内容会保留')
        assert page.locator('.auth-card').evaluate('el=>el.querySelector(".eyebrow").getBoundingClientRect().top>=el.querySelector(".auth-back").getBoundingClientRect().bottom'), 'auth navigation overlaps heading'
        page.get_by_role('button', name='注册', exact=True).click()
        expect(page.get_by_role('heading', name='创建你的账号')).to_be_visible()
        page.get_by_role('button', name='登录', exact=True).click()
        back()
        draft()

        page.get_by_role('button', name='点击上传，或将素材拖到这里', exact=False).click()
        expect(page.get_by_role('heading', name='欢迎回来')).to_be_visible()
        page.go_back()
        expect(page.get_by_role('heading', name='让想法，成为画面。')).to_be_visible()
        draft()
        page.locator('.upload-zone').evaluate("""el=>{
            const transfer=new DataTransfer();
            transfer.items.add(new File(['测试参考文稿'], 'guest-reference.txt', {type:'text/plain'}));
            el.dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:transfer}));
        }""")
        expect(page.get_by_role('heading', name='欢迎回来')).to_be_visible()
        back()
        expect(page.locator('.file-list')).to_contain_text('guest-reference.txt')

        page.locator('.source-form').get_by_role('button', name='搜索', exact=True).click()
        expect(page.get_by_role('heading', name='欢迎回来')).to_be_visible()
        assert not any(method == 'POST' and path in ['/api/jobs', '/api/sources/search', '/api/sources/ingest'] for method, path in requests)
        page.screenshot(path=str(ARTIFACTS / 'contextual-login.png'), full_page=True)
        login()
        draft()
        expect(page.locator('.file-list')).to_contain_text('guest-reference.txt')
        expect(page.locator('.api-state')).to_contain_text('API 已配置')
        assert not any(method == 'POST' and path == '/api/jobs' for method, path in requests)
        # Simulate status updates to check the progress indicator without paid generation.
        fixture={'id':'ui-progress-fixture','prompt':'进度显示验收','style':'studio_sketch','duration':90,'status':'running','stage':'outline'}
        page.route('**/api/jobs',lambda route:route.fulfill(json=[fixture]))
        page.route('**/api/jobs/ui-progress-fixture/planning',lambda route:route.fulfill(json={'status':'awaiting_review','pending_stage':'storyboard','auto_approve':False,'documents':{}}))
        for status,stage,title in [('running','outline','打磨内容'),('awaiting_review','outline','打磨内容'),('revising','storyboard','打磨内容'),('running','render','收获作品')]:
            fixture.update(status=status,stage=stage)
            page.evaluate('window.dispatchEvent(new Event("focus"))')
            expect(page.locator('.creation-steps [aria-current=step]')).to_have_count(1)
            expect(page.locator('.creation-steps [aria-current=step]')).to_contain_text(title)
        fixture.update(status='complete',stage='compose')
        page.evaluate('window.dispatchEvent(new Event("focus"))')
        expect(page.locator('.creation-steps [aria-current=step]')).to_contain_text('描述想法')
        page.get_by_role('button',name='预览 进度显示验收',exact=True).click()
        expect(page.locator('.creation-steps [aria-current=step]')).to_contain_text('收获作品')
        page.locator('#prompt').fill(PROMPT+'检查')
        page.locator('#prompt').fill(PROMPT)
        expect(page.locator('.creation-steps [aria-current=step]')).to_contain_text('描述想法')
        page.unroute('**/api/jobs')
        page.unroute('**/api/jobs/ui-progress-fixture/planning')
        page.evaluate('window.dispatchEvent(new Event("focus"))')
        expect(page.get_by_role('button',name='预览 进度显示验收',exact=True)).to_have_count(0)
        draft()
        page.locator('.sidebar').get_by_role('button', name='我的作品', exact=False).click()
        expect(page.locator('.library-tools')).to_be_visible()
        expect(page.locator('.job-card').first).to_be_visible()
        page.locator('[name=job-search]').fill('no-matching-work-acceptance-87124')
        expect(page.get_by_text('没有匹配的作品', exact=True)).to_be_visible()
        expect(page.locator('.job-card')).to_have_count(0)
        page.get_by_role('button', name='清除筛选', exact=True).click()
        page.locator('.library-filters').get_by_role('button', name='已完成', exact=True).click()
        expect(page.locator('.job-card').first).to_be_visible()
        expect(page.locator('.job-status')).to_have_count(0)
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ARTIFACTS / 'library-desktop.png'), full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'), 'library overflow'
        page.screenshot(path=str(ARTIFACTS / 'library-mobile.png'), full_page=True)
        page.set_viewport_size({'width':1440,'height':1050})
        page.get_by_role('button', name='配置', exact=True).click()
        expect(page.get_by_role('heading', name='模型配置', exact=True)).to_be_visible()
        expect(page.locator('[name=text_api_key]')).to_have_value('')
        expect(page.locator('[name=vision_api_key]')).to_have_value('')
        page.screenshot(path=str(ARTIFACTS / 'settings-desktop.png'), full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(ARTIFACTS / 'settings-mobile.png'), full_page=True)
        page.get_by_role('button', name='退出登录', exact=True).click()
        expect(page.get_by_role('button', name='登录', exact=True)).to_be_visible()
        expect(page.locator('#prompt')).to_have_value('')
        expect(page.locator('.job-card')).to_have_count(0)
        expect(page.locator('.file-list')).to_have_count(0)
        assert context.request.get(BASE + '/api/jobs').status == 401

        # A direct private route must return to that view after authenticating.
        page.goto(BASE + '/#wallet', wait_until='networkidle')
        expect(page.get_by_role('heading', name='欢迎回来')).to_be_visible()
        login()
        expect(page.get_by_role('heading', name='余额与流水', exact=True)).to_be_visible()
        page.get_by_role('button', name='退出登录', exact=True).click()
        expect(page.get_by_role('button', name='登录', exact=True)).to_be_visible()

        for width, height in [(768,1024),(390,844),(320,800)]:
            page.set_viewport_size({'width':width,'height':height})
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'), ('guest overflow',width)
            page.screenshot(path=str(ARTIFACTS / f'guest-{width}.png'), full_page=True)
            page.get_by_role('button', name='免费注册', exact=True).click()
            expect(page.get_by_role('heading', name='创建你的账号')).to_be_visible()
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'), ('auth overflow',width)
            page.screenshot(path=str(ARTIFACTS / f'register-{width}.png'), full_page=True)
            back()
        page.emulate_media(reduced_motion='reduce')
        assert page.locator('.theme-card').first.evaluate('el=>getComputedStyle(el).transitionDuration') == '1e-05s'
        assert_safe_storage(page)
        assert not errors, errors
        report={'guest_entry':True,'no_private_background_requests':True,'protected_endpoints':True,
                'login_on_action':True,'draft_and_local_file_preserved':True,'private_route_return':True,
                'logout_clears_workspace':True,'library_search_and_filters':True,'desktop_and_mobile':True,'no_jobs_submitted':True}
        (ARTIFACTS/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('PASS: public creator, protected actions, draft/file retention, login return, logout cleanup, private API isolation, responsive layout, reduced motion; no generation calls.')
    finally:
        context.request.post(BASE + '/api/auth/logout', headers={'X-Frame-Request':'1'})
        browser.close()
