"""Verify the actual revised film, original comparison, playback and usage."""
import hashlib,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from browser_helpers import dismiss_guide
ROOT=Path(__file__).resolve().parents[1];BASE='https://vedio.myaihub.asia:8443'
OUT=ROOT/'.tmp/revision-browser';receipt=json.loads((OUT/'receipt.json').read_text());child=receipt['child'];parent=receipt['parent']
credentials=dict(line.split('=',1) for line in (ROOT/'.tmp/staging/private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 b=p.chromium.launch();ctx=b.new_context(viewport={'width':1440,'height':1050});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/#login');page.locator('[name=username]').fill(credentials['USERNAME']);page.locator('[name=password]').fill(credentials['PASSWORD']);page.get_by_role('button',name='登录工作空间',exact=True).click();page.locator('#prompt').wait_for();dismiss_guide(page)
 job=ctx.request.get(BASE+'/api/jobs/'+child).json();assert job['status']=='complete' and job['revision_parent']==parent and job['review']['passed'],job
 page.locator('.sidebar').get_by_role('button',name='我的作品',exact=True).click()
 page.locator('.job-card').filter(has=page.locator('a[href="/api/jobs/'+child+'/video"]')).get_by_role('button',name='预览 ',exact=False).click()
 video=page.get_by_label('视频成品预览');expect(video).to_be_visible();video.evaluate('(v)=>v.play()')
 page.wait_for_function('()=>document.querySelector("[aria-label=视频成品预览]").currentTime>.2')
 assert 59.9<video.evaluate('(v)=>v.duration')<60.2
 expect(page.locator('.film-version')).to_contain_text('2')
 page.get_by_role('button',name='查看原版',exact=True).click();expect(video).to_have_attribute('src','/api/jobs/'+parent+'/video')
 expect(page.locator('.film-version')).to_contain_text('1')
 page.screenshot(path=str(OUT/'original-comparison.png'),full_page=True)
 for suffix in ['video','subtitles']:
  response=ctx.request.get(BASE+'/api/jobs/'+child+'/'+suffix,headers={'Range':'bytes=0-1023'} if suffix=='video' else {})
  assert response.status==(206 if suffix=='video' else 200),(suffix,response.status)
  assert len(response.body())>20
 usage=ctx.request.get(BASE+'/api/jobs/'+child+'/usage').json();assert usage['events'] and any(e.get('metered') for e in usage['events'])
 for name,value in receipt['original_hashes'].items():assert hashlib.sha256((Path(receipt['project'])/'output'/name).read_bytes()).hexdigest()==value
 assert not errors,errors
 receipt.update(complete=True,video_reviewed=True,usage_calls=len(usage['events']),original_unchanged=True)
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));b.close()
print('PASS: revised film complete with fresh model review, 60s playback, original comparison, authenticated downloads, real usage and unchanged original hashes.')
