"""Browser acceptance of every public, actually generated video example."""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('C2V_CHECK_URL','https://vedio.myaihub.asia:8443')
samples=json.loads((ROOT/'templates/showcase.json').read_text())
catalog={x['id']:x for x in json.loads((ROOT/'templates/catalog.json').read_text())}
out=ROOT/'.tmp/gallery-acceptance';out.mkdir(exist_ok=True)
assert len(samples)==9 and len([s for s in samples if s['kind']=='creation'])==7
with sync_playwright() as p:
 browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1050})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE,wait_until='networkidle')
 assert page.request.get(BASE+'/api/auth/me').status==401
 expect(page.locator('#prompt')).to_be_visible()
 assert page.locator('.topbar').bounding_box()['height']==56
 for sample in samples:
  identity=sample['id']
  if sample['kind']=='creation':
   page.goto(BASE+'/#create',wait_until='networkidle')
   category={'learning':'讲清知识','story':'故事与产品','review':'笔记复盘'}[catalog[identity]['category']]
   page.get_by_role('button',name=category,exact=True).click()
   page.get_by_role('button',name='观看'+catalog[identity]['title']+'的真实示例',exact=True).click()
  else:
   page.goto(BASE+'/#edit',wait_until='networkidle')
   page.locator('.editing-samples button').nth(0 if identity=='edit-product' else 1).click()
  video=page.get_by_label('实际成片示例');expect(video).to_be_visible()
  expect(video).to_have_attribute('src','/showcase/'+identity+'.mp4')
  video.evaluate('(v)=>v.play()')
  page.wait_for_function('()=>document.querySelector("[aria-label=实际成片示例]").currentTime>.2')
  duration=video.evaluate('(v)=>v.duration')
  assert abs(duration-sample['duration'])<1,(identity,duration)
  video.evaluate('(v)=>{v.pause();v.currentTime=v.duration-1}')
  page.wait_for_function('()=>{const v=document.querySelector("[aria-label=实际成片示例]");return !v.seeking&&v.readyState>=2&&v.currentTime>=v.duration-1.1}')
  response=page.request.get(BASE+'/showcase/'+identity+'.mp4',headers={'Range':'bytes=0-1023'})
  assert response.status==206 and len(response.body())==1024
  assert page.request.get(BASE+'/showcase/'+identity+'.jpg').status==200
  expect(page.get_by_role('link',name='查看来源与许可')).to_be_visible()
  if identity in ['explainer','notes','edit-product']:
   for width,height in [(1440,1050),(390,844),(320,760)]:
    page.set_viewport_size({'width':width,'height':height})
    page.wait_for_function('()=>{const d=document.querySelector("[role=dialog]").getBoundingClientRect();const v=document.querySelector("[aria-label=实际成片示例]").getBoundingClientRect();return d.left>=0&&d.right<=innerWidth&&v.left>=d.left&&v.right<=d.right}')
    page.wait_for_timeout(250)
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    expect(video).to_be_visible()
    page.screenshot(path=str(out/f'{identity}-{width}.png'))
   page.set_viewport_size({'width':1440,'height':1050})
  page.keyboard.press('Escape')
  print('PASS public sample:',identity,round(duration,2),flush=True)
 assert not errors,errors
 assert page.request.get(BASE+'/showcase/SOURCES.md').status==200
 browser.close()
print('PASS: all 7 creation and 2 editing samples, guest access, playback/seek, Range downloads, source/license links and responsive modal')
