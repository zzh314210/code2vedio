"""Authenticated browser acceptance for a completed, model-generated exam video."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);args=parser.parse_args()
base='https://vedio.myaihub.asia'
credentials=dict(line.split('=',1) for line in (ROOT/'private/admin-access.txt').read_text().splitlines())
artifacts=ROOT/'.tmp/live-video-check';artifacts.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page()
 page.goto(base+'/#login',wait_until='networkidle');page.locator('[name=username]').fill(credentials['USERNAME']);page.locator('[name=password]').fill(credentials['PASSWORD'])
 page.get_by_role('button',name='登录工作空间').click();page.get_by_role('heading',name='让想法，成为画面。').wait_for()
 response=context.request.get(base+'/api/jobs/'+args.job);assert response.status==200
 job=response.json();assert job['status']=='complete',job['status'];assert job['review']['passed'],job['review']
 page.get_by_role('button',name='预览 '+job['prompt'],exact=True).click()
 video=page.locator('video');video.wait_for();page.wait_for_function('() => document.querySelector("video").readyState>=2')
 details=video.evaluate('(v)=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,tracks:v.textTracks.length})')
 assert abs(details['duration']-90)<0.3 and details['width']==1920 and details['height']==1080 and details['tracks']==1,details
 assert video.evaluate('(v)=>v.textTracks[0].mode')!='showing', 'Burned-in captions must not be duplicated by default'
 captions=context.request.get(base+'/api/jobs/'+args.job+'/subtitles');assert captions.status==200 and captions.text().startswith('WEBVTT')
 ranged=context.request.get(base+'/api/jobs/'+args.job+'/video',headers={'Range':'bytes=0-1023'});assert ranged.status==206 and len(ranged.body())==1024
 created=context.request.post(base+'/api/api-keys',data={'name':'real-video-acceptance'},headers={'X-Frame-Request':'1'})
 assert created.status==201
 token=created.json()
 api=p.request.new_context(base_url=base,extra_http_headers={'Authorization':'Bearer '+token['key']})
 try:
  polled=api.get('/api/jobs/'+args.job);assert polled.status==200 and polled.json()['status']=='complete'
  downloaded=api.get('/api/jobs/'+args.job+'/video',headers={'Range':'bytes=0-1023'});assert downloaded.status==206 and len(downloaded.body())==1024
  usage=api.get('/api/jobs/'+args.job+'/usage');assert usage.status==200 and usage.json()['events']
 finally:
  assert context.request.delete(base+'/api/api-keys/'+token['id'],headers={'X-Frame-Request':'1'}).status==200
 assert api.get('/api/jobs/'+args.job).status==401
 api.dispose()
 video.evaluate('(v)=>{v.currentTime=71.5;v.textTracks[0].mode="hidden"}')
 page.wait_for_function('() => !document.querySelector("video").seeking')
 page.wait_for_function('() => document.querySelector("video").textTracks[0].cues.length>0')
 page.screenshot(path=str(artifacts/(args.job+'-desktop.png')),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.screenshot(path=str(artifacts/(args.job+'-mobile.png')),full_page=True)
 assert context.request.post(base+'/api/auth/logout',headers={'X-Frame-Request':'1'}).status==200
 browser.close()
(artifacts/(args.job+'-acceptance.json')).write_text(json.dumps({'job':args.job,'media':details,'review':job['review'],'authenticated_playback':True,'subtitles':True,'range_download':True,'mobile_layout':True,'bearer_poll_and_download':True,'bearer_revoked':True},ensure_ascii=False,indent=2))
print('PASS: real generated video, vision review passed, 90s 1080p playback, WebVTT captions, authenticated Range download, desktop/mobile layout, bearer polling/download/revocation.')
