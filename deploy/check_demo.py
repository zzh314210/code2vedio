import os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
base='https://vedio.myaihub.asia';credentials=dict(line.split('=',1) for line in (ROOT/'private/admin-access.txt').read_text().splitlines())
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 context=browser.new_context(viewport={'width':1440,'height':1100})
 page=context.new_page();page.goto(base,wait_until='networkidle')
 page.locator('[name=username]').fill(credentials['USERNAME']);page.locator('[name=password]').fill(credentials['PASSWORD']);page.get_by_role('button',name='登录工作空间').click()
 page.get_by_role('heading',name='让想法，成为画面。').wait_for()
 page.get_by_role('button',name='预览 考公行测·牛吃草问题：看懂存量、增量与净消耗（原创手绘样片）',exact=True).click()
 video=page.locator('video');video.wait_for()
 page.wait_for_function('() => document.querySelector("video").readyState>=2')
 details=video.evaluate('(v)=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,tracks:v.textTracks.length})')
 assert 99<details['duration']<102 and details['width']==1920 and details['height']==1080 and details['tracks']==1,details
 captions=context.request.get(base+'/api/jobs/exam-sketch-demo/subtitles');assert captions.status==200 and captions.text().startswith('WEBVTT')
 range_response=context.request.get(base+'/api/jobs/exam-sketch-demo/video',headers={'Range':'bytes=0-1023'});assert range_response.status==206 and len(range_response.body())==1024
 video.evaluate('(v)=>{v.currentTime=43;v.textTracks[0].mode="showing"}')
 page.wait_for_function('() => !document.querySelector("video").seeking')
 page.screenshot(path=str(ROOT/'.tmp/user-system-check/demo-player.png'),full_page=True)
 assert context.request.get(base+'/internal/billing/settle').status==404
 browser.close()
print('PASS: production admin demo playback 1080p, 100s, authenticated range download, WebVTT captions and hidden internal API.')
