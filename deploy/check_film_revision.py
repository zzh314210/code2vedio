"""Real preview browser/model acceptance; keeps the original real film immutable.

Imports an accepted pipeline sample into the isolated preview account, then uses
the public UI for advice, revision, storyboard confirmation and rendering.
Never run against production; the fixture is explicitly an imported sample.
"""
import hashlib,json,os,shutil,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
from browser_helpers import dismiss_guide
BASE='https://vedio.myaihub.asia:8443'
OUT=ROOT/'.tmp/revision-browser';OUT.mkdir(exist_ok=True)
credentials=dict(line.split('=',1) for line in (ROOT/'.tmp/staging/private/admin-access.txt').read_text().splitlines())
source=ROOT/'video_projects/showcase-word_story-v4'
assert (source/'showcase_acceptance.json').is_file(),'Use an actually accepted film'
identity='revision-demo-'+str(int(time.time()))
target=ROOT/'.tmp/staging/projects'/('studio-'+identity)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def relocate(value):
 if isinstance(value,dict):return {k:relocate(v) for k,v in value.items()}
 if isinstance(value,list):return [relocate(v) for v in value]
 if isinstance(value,str):return value.replace(str(source),str(target))
 return value

with sync_playwright() as p:
 browser=p.chromium.launch();ctx=browser.new_context(viewport={'width':1440,'height':1050});page=ctx.new_page();errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/#login');page.locator('[name=username]').fill(credentials['USERNAME']);page.locator('[name=password]').fill(credentials['PASSWORD']);page.get_by_role('button',name='登录工作空间',exact=True).click();page.locator('#prompt').wait_for();dismiss_guide(page)
 user=ctx.request.get(BASE+'/api/auth/me').json()
 manifest=json.loads((source/'output/manifest.json').read_text())
 # Copy the saved inputs, real film, and real planning documents. No fabricated
 # render receipt and no changes to the original project's files.
 for directory in ['prompts','input','code/runtime','assets','output/assets']:
  if (source/directory).is_dir():shutil.copytree(source/directory,target/directory,ignore=shutil.ignore_patterns('__pycache__'))
 for name in ['manifest.json','outline.json','storyboard.json','storyboard_assets.json','materials.json','final.mp4','subtitles.srt','review_status.json']:
  original=source/'output'/name
  if original.exists():
   dest=target/'output'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
 for file in target.rglob('*.json'):
  file.write_text(json.dumps(relocate(json.loads(file.read_text())),ensure_ascii=False,indent=2))
 record={'id':identity,'owner_id':user['id'],'prompt':manifest['topic'],'style':'studio_editorial','duration':60,'template_id':'word_story','status':'complete','stage':'compose','created_at':time.time(),'updated_at':time.time(),'video':'/api/jobs/'+identity+'/video','subtitles':'/api/jobs/'+identity+'/subtitles','review':manifest['visual_review'],'message':'真实词汇示例导入，用于成片修改验收'}
 (target/'studio_job.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
 hashes={name:digest(target/'output'/name) for name in ['final.mp4','storyboard.json','outline.json']}
 page.reload();dismiss_guide(page)
 page.locator('.sidebar').get_by_role('button',name='我的作品',exact=True).click()
 card=page.locator('.job-card').filter(has=page.get_by_role('button',name='修改视频',exact=True)).first
 expect(card).to_be_visible();calls=[]
 page.on('request',lambda req:calls.append(req.url) if req.method=='POST' and req.url.endswith('/revision-advice') else None)
 card.get_by_role('button',name='修改视频',exact=True).click()
 expect(page.get_by_role('dialog')).to_contain_text('原片会保留');page.wait_for_timeout(700);assert not calls,'Opening dialog called the model'
 for width,height in [(390,844),(320,760),(1440,1050)]:
  page.set_viewport_size({'width':width,'height':height});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
  expect(page.get_by_role('button',name='生成修改版',exact=True)).to_be_visible();page.screenshot(path=str(OUT/f'dialog-{width}.png'))
 page.get_by_role('button',name='AI 帮我看看',exact=True).click()
 deadline=time.time()+240
 while time.time()<deadline:
  state=ctx.request.get(BASE+'/api/jobs/'+identity+'/revision-advice').json()
  if state['status'] in ['ready','failed']:break
  page.wait_for_timeout(1500)
 assert state['status']=='ready',state
 expect(page.locator('.revision-advice')).to_be_visible(timeout=10000)
 if state['suggestions']:
  page.get_by_role('button',name='采用建议',exact=False).first.click();assert page.locator('#film-revision-feedback').input_value().strip()
 page.screenshot(path=str(OUT/'advice.png'))
 feedback='只修改最后的回忆题：请观众说出 abandon a plan 的中文意思，先提问，静默停顿至少2秒，再明确揭晓“放弃计划”。前面的香蕉船长故事、正确词义、例句、手绘/图解配色均保持，目标时长仍为60秒。'
 page.locator('#film-revision-feedback').fill(feedback)
 with page.expect_response(lambda response:response.url.endswith('/revisions') and response.request.method=='POST') as response:
  page.get_by_role('button',name='生成修改版',exact=True).click()
 result=response.value.json();assert response.value.status==202,result
 child=result['id'];print('Real revision created:',child,flush=True)
 receipt={'parent':identity,'child':child,'project':str(target),'original_hashes':hashes,'advice_count':len(state['suggestions']),'feedback':feedback,'created_at':time.time()}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
 deadline=time.time()+420
 while time.time()<deadline:
  job=ctx.request.get(BASE+'/api/jobs/'+child).json()
  if job['status'] in ['awaiting_review','failed','complete']:break
  page.wait_for_timeout(2000)
 assert job['status']=='awaiting_review' and job['stage']=='storyboard',job
 expect(page.locator('.revision-summary-note')).to_be_visible(timeout=15000)
 expect(page.get_by_role('button',name='确认分镜，开始制作',exact=True)).to_be_visible()
 plan=ctx.request.get(BASE+'/api/jobs/'+child+'/planning').json()
 story=plan['documents']['storyboard']['document']
 assert 'abandon a plan' in json.dumps(story,ensure_ascii=False)
 page.screenshot(path=str(OUT/'revised-storyboard.png'),full_page=True)
 page.get_by_role('button',name='确认分镜，开始制作',exact=True).click()
 assert all(digest(target/'output'/name)==value for name,value in hashes.items())
 assert not errors,errors
 receipt['storyboard_confirmed']=True;(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
 print('PASS: real opt-in AI advice, mobile dialog, editable suggestion, revision planning, manual confirmation, original hashes unchanged. Render continues:',child,flush=True)
 browser.close()
