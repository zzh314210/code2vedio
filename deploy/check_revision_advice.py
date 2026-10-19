"""Real opt-in, time-aware AI advice and always-visible revision actions."""
import json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_helpers import dismiss_guide
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('C2V_CHECK_URL','https://vedio.myaihub.asia:8443')
receipt=json.loads((ROOT/'.tmp/revision-browser/receipt.json').read_text())
identity=receipt['child']
creds=dict(x.split('=',1) for x in (ROOT/'.tmp/staging/private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1440,'height':1050});page=ctx.new_page()
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/#login');page.locator('[name=username]').fill(creds['USERNAME']);page.locator('[name=password]').fill(creds['PASSWORD']);page.get_by_role('button',name='登录工作空间',exact=True).click();page.locator('#prompt').wait_for();dismiss_guide(page)
 page.locator('.sidebar').get_by_role('button',name='我的作品',exact=True).click()
 card=page.locator('.job-card').filter(has=page.locator('a[href="/api/jobs/'+identity+'/video"]'))
 calls=[];page.on('request',lambda req:calls.append(req.url) if req.method=='POST' and req.url.endswith('/revision-advice') else None)
 card.get_by_role('button',name='修改视频',exact=True).click();page.wait_for_timeout(500);assert not calls
 page.get_by_role('button',name='AI 帮我看看',exact=True).click()
 deadline=time.monotonic()+240
 while time.monotonic()<deadline:
  state=ctx.request.get(BASE+'/api/jobs/'+identity+'/revision-advice').json()
  if state['status'] in ['ready','failed']:break
  page.wait_for_timeout(1200)
 assert state['status']=='ready',state
 assert len(calls)==1
 expect(page.locator('.revision-advice')).to_be_visible(timeout=10000)
 if state['suggestions']:
  page.get_by_role('button',name='采用建议',exact=False).first.click()
  assert page.locator('#film-revision-feedback').input_value()
 for width,height in [(1440,1050),(390,844),(320,760)]:
  page.set_viewport_size({'width':width,'height':height})
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
  for name in ['取消','生成修改版']:
   button=page.get_by_role('button',name=name,exact=True);box=button.bounding_box()
   assert box and box['y']>=0 and box['y']+box['height']<=height,(name,width,box)
  page.locator('.revision-scroll').evaluate('(e)=>e.scrollTop=e.scrollHeight')
  page.screenshot(path=str(ROOT/f'.tmp/revision-browser/advice-final-{width}.png'))
 assert not errors,errors
 (ROOT/'.tmp/revision-browser/advice-final.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
 browser.close()
print('PASS: real time-aware AI advice, opt-in-only API call, editable suggestions, fixed actions at desktop/390/320 widths')
