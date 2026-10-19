"""Browser acceptance of the real Go user panel and Python worker."""
import os,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
base=os.environ.get('C2V_CHECK_URL','http://127.0.0.1:7861')
credentials=dict(line.split('=',1) for line in (ROOT/'private/admin-access.txt').read_text().splitlines())
artifacts=ROOT/'.tmp/user-system-check';artifacts.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 context=browser.new_context(viewport={'width':1440,'height':1000})
 page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 response=page.goto(base,wait_until='networkidle');assert response.status==200
 assert page.get_by_role('heading',name='欢迎回来').is_visible()
 assert context.request.get(base+'/api/jobs').status==401
 page.locator('input[name=username]').fill(credentials['USERNAME']);page.locator('input[name=password]').fill(credentials['PASSWORD'])
 page.get_by_role('button',name='登录工作空间').click()
 page.get_by_role('heading',name='让想法，成为画面。').wait_for()
 page.screenshot(path=str(artifacts/'desktop-create.png'),full_page=True)
 page.get_by_role('button',name='试试复利讲解').click();assert page.locator('#prompt').input_value()
 page.get_by_role('button',name='配置',exact=True).click();page.get_by_role('heading',name='模型配置',exact=True).wait_for()
 assert page.get_by_role('link',name='前往中转站获取访问密钥').get_attribute('href')=='https://token.myaihub.asia'
 assert '阿里云' not in page.locator('body').inner_text()
 assert page.locator('input[name=text-model]').is_visible()
 assert page.locator('.voice-card').count()>=10
 with page.expect_response(lambda r:'/api/voices/zh-CN-XiaoxiaoNeural/sample' in r.url) as sample:
  page.get_by_role('button',name='试听 晓晓 2秒',exact=True).click()
 assert sample.value.status==200
 page.screenshot(path=str(artifacts/'desktop-settings.png'),full_page=True)
 page.locator('.sidebar').get_by_role('button',name='余额与流水',exact=True).click()
 page.get_by_role('heading',name='余额与流水',exact=True).wait_for()
 page.locator('.sidebar').get_by_role('button',name='账号与安全',exact=True).click()
 assert page.get_by_role('heading',name='修改密码').is_visible()
 page.locator('.sidebar').get_by_role('button',name='开放 API',exact=True).click()
 page.get_by_role('heading',name='视频 API 使用指南').wait_for()
 page.locator('#key-name').fill('browser-acceptance-'+str(int(time.time())))
 with page.expect_response(lambda r:r.url.endswith('/api/api-keys') and r.request.method=='POST') as key_result:
  page.get_by_role('button',name='创建调用密钥',exact=True).click()
 token=key_result.value.json();assert key_result.value.status==201
 # The bearer credential can read its own jobs, but cannot manage accounts.
 assert context.request.get(base+'/api/jobs',headers={'Authorization':'Bearer '+token['key']}).status==200
 assert context.request.get(base+'/api/admin/users',headers={'Authorization':'Bearer '+token['key']}).status==403
 assert context.request.delete(base+'/api/api-keys/'+token['id'],headers={'X-Frame-Request':'1'}).status==200
 page.get_by_role('button',name='已保存，隐藏',exact=True).click()
 page.locator('.sidebar').get_by_role('button',name='用户管理',exact=True).click()
 assert page.get_by_role('heading',name='用户管理',exact=True).is_visible()
 page.locator('.sidebar').get_by_role('button',name='创作视频',exact=False).click()
 page.locator('#source-query').fill('复利 原理')
 with page.expect_response(lambda r:r.url.endswith('/api/sources/search'),timeout=60000) as search:
  page.locator('.source-form').get_by_role('button',name='搜索',exact=True).click()
 assert search.value.status==200,search.value.text()
 assert len(search.value.json()['results'])>0
 page.screenshot(path=str(artifacts/'desktop-sources.png'),full_page=True)
 for width,height in [(390,844),(768,1024)]:
  page.set_viewport_size({'width':width,'height':height})
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),('overflow',width)
  page.screenshot(path=str(artifacts/f'mobile-{width}.png'),full_page=True)
  page.locator('.mobile-nav').get_by_role('button',name='模型配置',exact=True).click()
  assert page.get_by_role('heading',name='模型配置',exact=True).is_visible()
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),('settings overflow',width)
  page.screenshot(path=str(artifacts/f'settings-{width}.png'),full_page=True)
  page.locator('.mobile-nav').get_by_role('button',name='新建视频',exact=True).click()
 assert page.evaluate('localStorage.length===0 && sessionStorage.length===0')
 assert not errors,errors
 page.get_by_role('button',name='退出登录').click();page.get_by_role('heading',name='欢迎回来').wait_for()
 assert context.request.get(base+'/api/jobs').status==401
 browser.close()
print('PASS: public login page; real Go login, panel, free voice sample, model settings, balance, admin, API key permissions/revocation, live source search, mobile layouts, logout; no paid API calls.')
