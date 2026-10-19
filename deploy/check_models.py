"""Model configuration interaction checks; catalogs are mocked, no paid calls or saved changes."""
from browser_helpers import dismiss_guide, assert_safe_storage
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
base=os.environ.get('C2V_CHECK_URL','https://vedio.myaihub.asia')
credentials=dict(line.split('=',1) for line in (ROOT/'private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 context=browser.new_context(viewport={'width':1440,'height':1050})
 page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(base+'/#login',wait_until='networkidle')
 page.locator('[name=username]').fill(credentials['USERNAME']);page.locator('[name=password]').fill(credentials['PASSWORD'])
 page.get_by_role('button',name='登录工作空间').click()
 page.get_by_role('heading',name='让想法，成为画面。').wait_for()
 dismiss_guide(page)
 assert context.request.get(base+'/api/voices').status==200
 page.get_by_role('button',name='配置',exact=True).click()
 page.get_by_role('heading',name='模型配置',exact=True).wait_for()
 reuse=page.get_by_role('checkbox',name='复用内容生成配置（可选）',exact=False)
 if reuse.is_checked(): reuse.uncheck()
 for name in ('text_api_key','vision_api_key'):
  assert page.locator('[name='+name+']').is_visible()
 assert page.get_by_role('button',name='获取内容生成模型列表',exact=True).is_visible()
 assert page.get_by_role('button',name='获取视觉审核模型列表',exact=True).is_visible()
 # Real authenticated Go endpoint validates private targets without contacting a model service.
 rejected=context.request.post(base+'/api/config/models',headers={'X-Frame-Request':'1'},data={'role':'text','base_url':'https://127.0.0.1/v1','api_key':'dummy'})
 assert rejected.status==422
 assert context.request.get(base+'/api/auth/me').status==200
 mode={'failure':False};requests=[]
 def catalog(route):
  body=route.request.post_data_json;requests.append(body)
  if mode['failure']:
   route.fulfill(status=422,content_type='application/json',body=json.dumps({'detail':'此接口未提供模型列表，请按服务商说明手动填写模型名称。'}));return
  route.fulfill(status=200,content_type='application/json',body=json.dumps({'models':['sample-alpha','sample-vision','sample-writing']}))
 page.route('**/api/config/models',catalog)
 page.locator('[name=text-url]').fill('https://example.com/v1')
 page.locator('[name=text_api_key]').fill('dummy-text-key')
 page.locator('[name=text-model]').fill('manual-model')
 page.get_by_role('button',name='获取内容生成模型列表',exact=True).click()
 page.get_by_role('status').filter(has_text='已获取 3 个模型').wait_for()
 assert page.locator('[name=text-model]').input_value()=='manual-model'
 page.get_by_role('searchbox',name='搜索内容生成模型').fill('writing')
 choices=page.get_by_role('combobox',name='内容生成可用模型',exact=True)
 assert choices.locator('option').count()==2
 choices.select_option('sample-writing')
 assert page.locator('[name=text-model]').input_value()=='sample-writing'
 assert requests[-1]['role']=='text' and requests[-1]['api_key']=='dummy-text-key'
 page.locator('[name=vision-url]').fill('https://example.org/v1')
 page.locator('[name=vision_api_key]').fill('dummy-vision-key')
 page.get_by_role('button',name='获取视觉审核模型列表',exact=True).click()
 page.get_by_role('combobox',name='视觉审核可用模型',exact=True).select_option('sample-vision')
 assert page.locator('[name=vision-model]').input_value()=='sample-vision'
 assert requests[-1]['role']=='vision' and requests[-1]['api_key']=='dummy-vision-key'
 assert page.locator('[name=text-model]').input_value()=='sample-writing'
 mode['failure']=True
 page.get_by_role('button',name='获取内容生成模型列表',exact=True).click()
 page.get_by_role('alert').filter(has_text='此接口未提供模型列表').wait_for()
 page.locator('[name=text-model]').fill('manual-after-error')
 assert page.locator('[name=text-model]').input_value()=='manual-after-error'
 # Changed endpoint clears the old catalog, without changing the independent vision selection.
 page.locator('[name=vision-url]').fill('https://example.net/v1')
 assert page.get_by_role('combobox',name='视觉审核可用模型',exact=True).count()==0
 mode['failure']=False
 page.get_by_role('button',name='获取内容生成模型列表',exact=True).click()
 page.get_by_role('combobox',name='内容生成可用模型',exact=True).wait_for()
 for width,height in ((1440,1050),(390,844)):
  page.set_viewport_size({'width':width,'height':height})
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),('overflow',width)
  page.screenshot(path=str(ROOT/f'.tmp/user-system-check/models-{width}.png'),full_page=True)
 assert not errors,errors
 assert context.request.post(base+'/api/auth/logout',headers={'X-Frame-Request':'1'}).status==200
 browser.close()
print('PASS: independent Chinese model settings, manual entry, list filtering/selection, error fallback, no unsaved credential persistence, endpoint change invalidation, mobile layout; mocked catalogs, no paid calls.')
