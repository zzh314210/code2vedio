"""Real staging result: public sample, owned source seeks, playback and downloads."""
from pathlib import Path
import os
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE=os.environ.get('C2V_CHECK_URL','http://127.0.0.1:7861')
creds=dict(x.split('=',1) for x in (ROOT/'.tmp/staging/private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/#edit',wait_until='networkidle')
 page.locator('.editing-samples button').first.click();v=page.get_by_label('实际成片示例');v.wait_for()
 v.evaluate('(v)=>v.play()');page.wait_for_function("()=>document.querySelector('[aria-label=实际成片示例]').currentTime>0.2")
 assert 58<v.evaluate('(v)=>v.duration')<60
 page.keyboard.press('Escape');page.get_by_role('button',name='登录并开始剪辑',exact=True).click()
 page.locator('[name=username]').fill(creds['USERNAME']);page.locator('[name=password]').fill(creds['PASSWORD']);page.get_by_role('button',name='登录工作空间').click();page.locator('.edit-history').wait_for()
 jobs=page.request.get(BASE+'/api/edits').json();job=next(j for j in jobs if j['id']=='e5e0045ed1c3')
 page.locator('.edit-history button').filter(has_text=job['prompt']).click();expect(page.get_by_label('剪辑成品预览')).to_be_visible()
 page.get_by_role('button',name='预览第1段',exact=True).click();v=page.get_by_label('选段原片预览');v.wait_for();page.wait_for_function('(n)=>Math.abs(document.querySelector("[aria-label=选段原片预览]").currentTime-n)<0.15',arg=job['plan']['clips'][0]['start'])
 page.get_by_role('button',name='预览第2段',exact=True).click();page.wait_for_function('(n)=>Math.abs(document.querySelector("[aria-label=选段原片预览]").currentTime-n)<0.15',arg=job['plan']['clips'][1]['start'])
 v.evaluate('(v)=>v.play()');page.wait_for_function('(n)=>document.querySelector("[aria-label=选段原片预览]").currentTime>n+0.3',arg=job['plan']['clips'][1]['start'])
 v.evaluate('(v)=>v.pause()')
 for kind in ['video','subtitles','project']:
  response=page.request.get(BASE+'/api/edits/'+job['id']+'/'+kind,headers={'Range':'bytes=0-1023'} if kind=='video' else {})
  assert response.status==(206 if kind=='video' else 200),(kind,response.status)
  assert len(response.body())>10
 # Effects alone must preserve proofread captions. Intercept only this save,
 # keeping the completed real fixture intact for playback/download regression.
 saved=[]
 def effect_save(route):
  saved.append(route.request.post_data_json);route.fulfill(json=job)
 page.route('**/api/edits/'+job['id']+'/plan',effect_save)
 page.locator('.edit-timeline select').first.select_option('focus')
 page.get_by_role('button',name='保存方案',exact=True).click()
 expect(page.get_by_role('button',name='保存方案',exact=True)).to_be_disabled()
 assert saved and saved[0]['subtitles']==job['plan']['subtitles'],'Effect change lost proofread subtitles'
 page.unroute('**/api/edits/'+job['id']+'/plan',effect_save)
 page.locator('.sidebar').get_by_role('button',name='我的作品',exact=True).click();page.locator('.edit-library .job-thumbnail').filter(has=page.locator('img')).first.wait_for()
 page.locator('.edit-library .job-thumbnail').filter(has_text='剪辑完成').last.click();expect(page.get_by_label('剪辑成品预览')).to_be_visible()
 page.reload(wait_until='networkidle');expect(page.locator('.edit-history')).to_be_visible()
 assert not errors,errors
 b.close()
print('PASS: real public sample playback, completed editing playback, same-source seek changes, authenticated Range/SRT/OTIO downloads, unified gallery, reload.')
