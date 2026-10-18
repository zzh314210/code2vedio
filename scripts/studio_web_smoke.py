"""Real Chromium acceptance checks; optional real pipeline generation."""
import argparse,json,re,time,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--generate',action='store_true');p.add_argument('--retry',action='store_true');a=p.parse_args()
images=ROOT/'.tmp/web-acceptance';images.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:7860');page.wait_for_load_state('networkidle')
    assert page.get_by_role('button',name='生成视频',exact=True).is_disabled()
    page.screenshot(path=str(images/'desktop.png'),full_page=True)
    page.get_by_role('button',name='试试复利讲解').click()
    assert page.get_by_role('button',name='生成视频',exact=True).is_enabled()
    with tempfile.TemporaryDirectory() as upload_tmp:
        material=Path(upload_tmp)/'pipeline-test.md';material.write_text('Generic uploaded teaching material.',encoding='utf8')
        page.locator('input[type=file]').set_input_files(str(material))
        assert page.get_by_text('pipeline-test.md',exact=True).is_visible()
        page.get_by_role('button',name='移除 pipeline-test.md').click()
    page.locator('.theme-card').filter(has_text='手绘课堂').click()
    assert page.locator('.theme-card').filter(has_text='手绘课堂').get_attribute('aria-pressed')=='true'
    page.get_by_role('button',name='配置',exact=True).click()
    assert page.get_by_role('dialog').is_visible()
    assert page.locator('#text-key').get_attribute('type')=='password'
    assert page.locator('#speech-provider').is_visible()
    config=page.request.get('http://127.0.0.1:7860/api/config').json()
    if config.get('speech_sample_available'):
        assert page.get_by_label('本地男老师配音试听').is_visible()
        response=page.request.get('http://127.0.0.1:7860/api/speech/sample')
        assert response.ok and response.body()[:4]==b'RIFF'
    else:
        assert page.get_by_label('本地男老师配音试听').count()==0

    page.screenshot(path=str(images/'configuration.png'))
    page.get_by_role('button',name='保存配置').click()
    page.get_by_role('button',name='配置已保存').wait_for()
    page.set_viewport_size({'width':375,'height':667})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.get_by_role('button',name='返回创作').scroll_into_view_if_needed()
    page.screenshot(path=str(images/'configuration-375.png'))
    page.get_by_role('button',name='返回创作').click()
    for width,height in [(390,844),(768,1024),(1024,900)]:
        page.set_viewport_size({'width':width,'height':height})
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),f'Overflow at {width}'
        page.screenshot(path=str(images/f'responsive-{width}.png'),full_page=True)
    assert page.evaluate('localStorage.length===0&&sessionStorage.length===0')
    page.set_viewport_size({'width':1440,'height':1050})
    if a.generate:
        with page.expect_response(lambda r:r.url.endswith('/api/jobs') and r.request.method=='POST') as response:
            page.get_by_role('button',name='生成视频',exact=True).click()
        payload=response.value.json();assert response.value.status==202,payload
        (images/'generated-job.json').write_text(json.dumps(payload),encoding='utf8')
        print('REAL_GENERATION_JOB',payload['id'],flush=True)
    if a.retry:
        with page.expect_response(lambda r:r.url.endswith('/retry') and r.request.method=='POST') as response:
            page.get_by_role('button',name='继续生成',exact=True).click()
        assert response.value.status==202,response.value.text()
        print('REAL_RETRY_JOB',response.value.json()['id'],flush=True)
    assert not errors,errors
    print('PASS: React rendering, theme selection, prompt input, upload/removal, configuration save, 390/768/1024 responsive, credentials absent from browser storage.',flush=True)
    browser.close()
