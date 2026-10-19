"""Live onboarding acceptance, without generating videos or changing configuration."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
from browser_helpers import assert_safe_storage

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('C2V_CHECK_URL','https://vedio.myaihub.asia').rstrip('/')
ARTIFACTS=ROOT/'.tmp/guide-check'
ARTIFACTS.mkdir(parents=True,exist_ok=True)
CREDENTIALS=dict(line.split('=',1) for line in (ROOT/'private/admin-access.txt').read_text().splitlines())
TITLES=['连接你的模型服务','说清你想做什么视频','补充素材，让内容更准确','选择风格和声音','先确认内容，再制作','作品会保存在这里']

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1050})
    page=context.new_page()
    errors,requests=[],[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda r:requests.append((r.method,urlsplit(r.url).path)))

    def login():
        page.locator('[name=username]').fill(CREDENTIALS['USERNAME'])
        page.locator('[name=password]').fill(CREDENTIALS['PASSWORD'])
        page.get_by_role('button',name='登录工作空间',exact=True).click()
        expect(page.locator('.auth-page')).to_have_count(0)

    def step(index):
        expect(page.locator('.driver-popover-title')).to_have_text(TITLES[index])
        expect(page.locator('.driver-popover-progress-text')).to_have_text(f'{index+1} / 6')
        page.wait_for_function('''() => {
            const b=document.querySelector('.studio-guide')?.getBoundingClientRect();
            return b && b.x>=0 && b.y>=0 && b.right<=innerWidth+1 && b.bottom<=innerHeight+1;
        }''')
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        expect(page.locator('.driver-active-element')).to_have_count(1)
        expect(page.locator('.driver-active-element')).to_be_visible()

    try:
        page.goto(BASE,wait_until='networkidle')
        expect(page.locator('.studio-guide')).to_have_count(0)
        page.locator('#prompt').fill('制作一个60秒的手绘考试题目讲解视频。')
        page.locator('#duration').select_option('60')
        page.get_by_role('button',name='使用引导',exact=True).click()
        step(0)
        page.screenshot(path=str(ARTIFACTS/'guest-desktop.png'))
        page.keyboard.press('Escape')
        expect(page.locator('.studio-guide')).to_have_count(0)
        expect(page.get_by_role('button',name='使用引导',exact=True)).to_be_focused()
        page.get_by_role('button',name='登录',exact=True).click()
        login()
        # A guest dismissal must not suppress the first signed-in tour.
        step(0)
        page.get_by_role('button',name='下一步',exact=True).click()
        step(1)
        page.get_by_role('button',name='上一步',exact=True).click()
        step(0)
        page.get_by_role('button',name='跳过使用引导',exact=True).click()
        expect(page.locator('#prompt')).to_have_value('制作一个60秒的手绘考试题目讲解视频。')
        expect(page.locator('#duration')).to_have_value('60')
        page.reload(wait_until='networkidle')
        expect(page.locator('.api-state')).to_contain_text('API 已配置')
        page.wait_for_timeout(700)
        expect(page.locator('.studio-guide')).to_have_count(0)

        for width,height in [(1440,1050),(390,844),(320,640)]:
            page.set_viewport_size({'width':width,'height':height})
            page.emulate_media(reduced_motion='reduce')
            page.locator('#prompt').fill('保留这份需求，引导只说明操作。')
            page.get_by_role('button',name='使用引导',exact=True).click()
            for i in range(6):
                step(i)
                if i in (0,3,5):
                    page.screenshot(path=str(ARTIFACTS/f'{width}-step-{i+1}.png'))
                # Keyboard focus must stay in the guide.
                for _ in range(5):
                    page.keyboard.press('Tab')
                    assert page.evaluate('Boolean(document.activeElement.closest(".studio-guide"))')
                page.get_by_role('button',name='开始创作' if i==5 else '下一步',exact=True).click()
            expect(page.locator('.studio-guide')).to_have_count(0)
            expect(page.locator('#prompt')).to_have_value('保留这份需求，引导只说明操作。')
            expect(page.locator('#prompt')).to_be_focused()
        assert_safe_storage(page)
        assert not errors,errors
        assert not any(method=='POST' and path in ['/api/jobs','/api/config','/api/sources/search','/api/sources/ingest'] for method,path in requests)
        page.get_by_role('button',name='退出登录',exact=True).click()
        expect(page.get_by_role('button',name='登录',exact=True)).to_be_visible()
        expect(page.locator('.driver-overlay')).to_have_count(0)
        assert context.request.get(BASE+'/api/jobs').status==401
    finally:
        context.request.post(BASE+'/api/auth/logout',headers={'X-Frame-Request':'1'})
        context.close()

    # Browser privacy restrictions must not break the optional guide.
    blocked=browser.new_context(viewport={'width':390,'height':844})
    blocked.add_init_script('''Storage.prototype.getItem=function(){throw new DOMException('Blocked','SecurityError')};
        Storage.prototype.setItem=function(){throw new DOMException('Blocked','SecurityError')};''')
    page=blocked.new_page()
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE,wait_until='networkidle')
    page.get_by_role('button',name='使用引导',exact=True).click()
    expect(page.locator('.studio-guide')).to_be_visible()
    page.get_by_role('button',name='跳过使用引导',exact=True).click()
    expect(page.locator('.studio-guide')).to_have_count(0)
    assert not errors,errors
    blocked.close()
    browser.close()

(ARTIFACTS/'acceptance.json').write_text(json.dumps({'guest_opt_in':True,'first_login_auto':True,
    'skip_and_replay':True,'remember_per_user':True,'six_steps':True,'draft_preserved':True,
    'desktop_mobile_keyboard':True,'blocked_storage':True,'no_generation':True},indent=2))
print('PASS: guest opt-in, first login tour, six steps, skip/replay/remember, unchanged draft, desktop/mobile keyboard navigation, storage fallback; no generation calls.')
