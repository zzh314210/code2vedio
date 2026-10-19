from pathlib import Path
import os
BASE=os.environ.get("C2V_CHECK_URL","http://127.0.0.1:7861")
from browser_helpers import dismiss_guide
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'.tmp/staging/screens';out.mkdir(exist_ok=True)
creds=dict(x.split('=',1) for x in (ROOT/'.tmp/staging/private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE,wait_until='networkidle');expect(page.locator('#prompt')).to_be_visible();page.screenshot(path=str(out/'guest.png'))
 page.locator('.sidebar').get_by_role('button',name='AI 剪辑',exact=True).click();expect(page.get_by_role('heading',name='把已有视频，剪成值得看的短片')).to_be_visible();page.screenshot(path=str(out/'edit-guest.png'),full_page=True)
 page.get_by_role('button',name='登录并开始剪辑',exact=True).click();page.locator('[name=username]').fill(creds['USERNAME']);page.locator('[name=password]').fill(creds['PASSWORD']);page.get_by_role('button',name='登录工作空间').click();page.locator('#edit-prompt').wait_for()
 page.locator('#edit-prompt').fill('保留商品演示和完整优惠条件，删除闲聊。')
 page.locator('.heading-tools').get_by_role('button',name='模型配置',exact=True).click()
 page.locator('.sidebar').get_by_role('button',name='AI 剪辑',exact=True).click()
 expect(page.locator('#edit-prompt')).to_have_value('保留商品演示和完整优惠条件，删除闲聊。')
 for width,height in [(1440,1050),(390,844)]:
  page.set_viewport_size({'width':width,'height':height});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),('edit overflow',width);page.screenshot(path=str(out/f'edit-{width}.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':1050})
 page.locator('.sidebar').get_by_role('button',name='创作视频',exact=True).click();dismiss_guide(page)
 page.locator('#prompt').fill('这是我的普通创作草稿，请不要被笔记复盘覆盖。')
 page.locator('.sidebar').get_by_role('button',name='笔记放映室',exact=True).click();expect(page.locator('#duration')).to_have_value('180');expect(page.get_by_role('heading',name='上传学习笔记')).to_be_visible();expect(page.locator('#prompt')).not_to_have_value('这是我的普通创作草稿，请不要被笔记复盘覆盖。');
 page.locator('#prompt').fill('重点复盘导数')
 page.locator('.sidebar').get_by_role('button',name='创作视频',exact=True).click();dismiss_guide(page)
 expect(page.locator('#prompt')).to_have_value('这是我的普通创作草稿，请不要被笔记复盘覆盖。')
 page.locator('.sidebar').get_by_role('button',name='笔记放映室',exact=True).click()
 expect(page.locator('#prompt')).to_have_value('重点复盘导数');page.screenshot(path=str(out/'notes.png'),full_page=True)
 for width,height in [(390,844),(768,1024)]:
  page.set_viewport_size({'width':width,'height':height});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),('notes overflow',width);page.screenshot(path=str(out/f'notes-{width}.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':1050})
 page.get_by_role('button',name='一分钟使用引导',exact=True).click()
 expect(page.locator('.driver-popover-title')).to_have_text('先上传你自己的笔记')
 for i in range(3):page.get_by_role('button',name='下一步',exact=True).click()
 page.get_by_role('button',name='开始创作',exact=True).click()
 # Notes can be created from an uploaded document without inventing a prompt.
 page.locator('#prompt').fill('')
 page.get_by_label('上传参考素材',exact=True).set_input_files(str(ROOT/'templates/examples/review-notes.md'))
 captured=[]
 def note_submit(route):
  if route.request.method=='POST':
   captured.append(route.request.post_data_buffer.decode('utf8'));route.fulfill(status=202,json={'id':'notes-browser-contract'})
  else:route.continue_()
 page.route('**/api/jobs',note_submit)
 page.get_by_role('button',name='生成视频',exact=True).click()
 expect(page.get_by_role('dialog')).to_contain_text('可以暂时离开')
 assert captured and 'review-notes.md' in captured[0] and 'notes' in captured[0] and '根据上传的笔记' in captured[0]
 assert not errors,errors
 b.close()
print('Staging guest, editing entry/login, note defaults and responsive layout passed.')
