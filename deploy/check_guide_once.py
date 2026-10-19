"""Browser acceptance for per-account onboarding cookies and reset behavior."""
import json,os,secrets
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE=os.environ.get('C2V_CHECK_URL','http://127.0.0.1:7861')
creds=dict(line.split('=',1) for line in (ROOT/'.tmp/staging/private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 b=p.chromium.launch();ctx=b.new_context(viewport={'width':1440,'height':1050});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def login():
  page.goto(BASE+'/#login');page.locator('[name=username]').fill(creds['USERNAME']);page.locator('[name=password]').fill(creds['PASSWORD']);page.get_by_role('button',name='登录工作空间',exact=True).click()
 def no_auto():
  page.wait_for_timeout(750);expect(page.locator('.studio-guide')).to_have_count(0)
 login();expect(page.locator('.studio-guide')).to_be_visible()
 flags=[c for c in ctx.cookies() if c['name'].startswith('frame.guide.seen.')];assert len(flags)==1 and flags[0]['value']=='1'
 assert flags[0]['sameSite']=='Lax' and flags[0]['path']=='/'
 # Reload before dismissing is still not a second first login.
 page.reload(wait_until='networkidle');no_auto()
 expect(page.get_by_text('新版体验区',exact=False)).to_have_count(0)
 expect(page.locator('.sidebar').get_by_role('button',name='模型配置',exact=True)).to_have_count(0)
 expect(page.locator('.heading-tools').get_by_role('button',name='模型配置',exact=True)).to_be_visible()
 expect(page.get_by_role('button',name='一分钟使用引导',exact=True)).to_be_visible()
 page.get_by_role('button',name='退出登录',exact=True).click();expect(page.get_by_role('button',name='登录',exact=True)).to_be_visible();login();no_auto()
 page.locator('.sidebar').get_by_role('button',name='笔记放映室',exact=True).click();no_auto()
 page.get_by_role('button',name='一分钟使用引导',exact=True).click();expect(page.locator('.driver-popover-title')).to_have_text('先上传你自己的笔记');page.get_by_role('button',name='跳过使用引导',exact=True).click()
 ctx.clear_cookies(name=flags[0]['name']);page.reload(wait_until='networkidle');expect(page.locator('.studio-guide')).to_be_visible();page.get_by_role('button',name='跳过使用引导',exact=True).click()
 # A different account in the same browser must get its own first-use marker.
 user='guide-check-'+secrets.token_hex(4);password=secrets.token_urlsafe(18)
 response=ctx.request.post(BASE+'/api/auth/register',data={'username':user,'password':password},headers={'X-Frame-Request':'1'});assert response.status==201,response.status
 page.goto(BASE+'/#create',wait_until='networkidle');page.reload(wait_until='networkidle');expect(page.locator('.studio-guide')).to_be_visible()
 flags=[c for c in ctx.cookies() if c['name'].startswith('frame.guide.seen.')];assert len(flags)==2
 page.get_by_role('button',name='跳过使用引导',exact=True).click();page.reload(wait_until='networkidle');no_auto()
 assert not errors,errors
 ctx.request.post(BASE+'/api/auth/logout',headers={'X-Frame-Request':'1'});ctx.close();b.close()
print('PASS: first-login only, reload during guide, logout/login, cross-page navigation, explicit replay, cookie reset, and per-account isolation. Latest controls/banner verified.')
