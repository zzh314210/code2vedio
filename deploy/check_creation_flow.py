"""Browser behavior contract: all references selectable, honest progress, no paid calls."""
from browser_helpers import dismiss_guide
from pathlib import Path
import json,time,os
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE=os.environ.get('C2V_CHECK_URL','https://vedio.myaihub.asia')
creds=dict(x.split('=',1) for x in Path(os.environ.get('C2V_CHECK_CREDENTIALS',str(ROOT/'private/admin-access.txt'))).read_text().splitlines())
out=ROOT/'.tmp/creation-check';out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch();c=b.new_context(viewport={'width':1440,'height':1050});page=c.new_page();errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/#login');page.locator('[name=username]').fill(creds['USERNAME']);page.locator('[name=password]').fill(creds['PASSWORD']);page.get_by_role('button',name='登录工作空间').click();page.locator('#prompt').wait_for();dismiss_guide(page)
 jobs=[]
 def jobs_route(route):
  if route.request.method=='POST':route.fulfill(status=202,json={'id':'fixture-job'})
  else:route.fulfill(json=jobs)
 page.route('**/api/jobs',jobs_route)
 sources=[{'id':'SRCfixture'+str(i),'title':'复利资料'+str(i),'url':'https://example.org/'+str(i),'text':'可读的完整复利参考正文。'*50} for i in range(3)]
 page.route('**/api/sources/search',lambda r:r.fulfill(json={'results':sources,'unreadable_count':1}))
 page.route('**/api/sources/SRCfixture*',lambda r:r.fulfill(json=next(s for s in sources if r.request.url.endswith(s['id']))))
 page.locator('#source-query').fill('复利');page.locator('.source-form').get_by_role('button',name='搜索',exact=True).click()
 expect(page.locator('.source-result')).to_have_count(3)
 for card in page.locator('.source-result').all():card.get_by_role('button',name='选为本片参考',exact=True).click()
 expect(page.locator('.selected-sources li')).to_have_count(3)
 page.locator('.source-result').nth(1).get_by_role('button',name='已选用 · 点击移除').click();expect(page.locator('.selected-sources li')).to_have_count(2)
 page.locator('.source-result').nth(2).get_by_role('button',name='预览正文').click();expect(page.get_by_role('dialog')).to_contain_text('完整复利参考正文');page.keyboard.press('Escape')
 page.screenshot(path=str(out/'sources.png'),full_page=True)
 page.locator('#prompt').fill('制作30秒复利原理说明，使用清晰图解。');page.locator('.review-mode input').check()
 page.get_by_role('button',name='生成视频',exact=True).click();expect(page.get_by_role('dialog')).to_contain_text('可以暂时离开');expect(page.get_by_role('dialog')).to_contain_text('6–15 分钟')
 page.screenshot(path=str(out/'submitted.png'))
 page.get_by_role('button',name='前往我的作品').click();expect(page.get_by_role('dialog')).to_have_count(0)
 jobs.append({'id':'fixture-job','prompt':'测试进度','style':'studio_sketch','duration':30,'status':'running','stage':'render','auto_approve':True,'stage_started_at':time.time()})
 page.evaluate("window.dispatchEvent(new Event('focus'))")
 expect(page.locator('.job-card .generation-progress')).to_contain_text('正在渲染画面');expect(page.locator('.job-card .generation-progress')).to_contain_text('预计还需')
 page.locator('.sidebar').get_by_role('button',name='创作视频',exact=False).click();expect(page.locator('.preview-panel .generation-progress')).to_contain_text('无需人工确认大纲与分镜')
 expect(page.locator('.pipeline-steps [aria-current=step]')).to_have_count(1)
 for width,height in [(1440,1050),(390,844)]:
  page.set_viewport_size({'width':width,'height':height});page.locator('.preview-panel .generation-progress').scroll_into_view_if_needed()
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
  page.screenshot(path=str(out/f'progress-{width}.png'))
 assert not errors,errors
 c.request.post(BASE+'/api/auth/logout',headers={'X-Frame-Request':'1'});b.close()
print('PASS: every search result selectable/removable, preview, submit modal, estimates, real phase states, desktop/mobile; mocked job submission, no model calls.')
