"""Actual Chromium UI interactions; isolated HTTP fixtures avoid changing live jobs."""
import copy
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.tmp/planning-acceptance';ART.mkdir(parents=True,exist_ok=True)
outline={'topic':'牛吃草：先理解净变化','target_audience':'突击备考考生','warnings':[],'sections':[{'id':'section_1','title':'草为何越来越少','goal':'理解净消耗','key_points':['每天都有新草长出','先抵消增长再计算消耗'],'sources':['WEB1'],'teaching_steps':['T1','T2','T3']}]}
story={'sections':[{'id':'section_1','title':'草为何越来越少','beats':[{'narration':'先看草场每天发生的两个变化。','caption':'增长与消耗','visual':'绿色箭头表示生长，橙色箭头表示牛吃草，同时出现后抵消相同部分。','duration_seconds':8,'lead_in_seconds':2,'teaching_step_ids':['T1','T2','T3'],'student_question':'为什么不能直接用牛数乘天数？','reasoning':'每天仍有新草生长，必须先扣除增长。'}]}]}
job={'id':'browser-fixture','prompt':'牛吃草问题的可视化讲解','style':'studio_sketch','duration':120,'status':'awaiting_review','stage':'outline','message':'大纲已就绪，请审核'}
snapshot={'status':'awaiting_review','pending_stage':'outline','auto_approve':False,'documents':{'outline':{'document':outline,'version':'a'*64,'approved':False}},'sources':[{'id':'WEB1','title':'牛吃草问题精讲','url':'https://www.eoffcn.com/kszx/detail/1070247.html'}],'teaching_plan':{'method':'净变化法','steps':[{'id':'T1','explanation':'观察两种同时发生的变化','why':'草在生长，牛也在吃草','visual_action':'两股反向变化同时运动'}]}}
actions=[]
def route_api(route):
 url=route.request.url.split('http://127.0.0.1:7860')[1]
 method=route.request.method
 if url=='/api/jobs':return route.fulfill(json=[job])
 if url.endswith('/planning') and method=='GET':return route.fulfill(json=snapshot)
 if '/planning/' in url and method=='PUT':
  value=route.request.post_data_json;stage=url.rsplit('/',1)[1];actions.append(('save',stage,value));snapshot['documents'][stage]={'document':value['document'],'version':'b'*64,'approved':False};return route.fulfill(json=snapshot)
 if url.endswith('/revise'):
  value=route.request.post_data_json;actions.append(('revise',value));snapshot['documents']['storyboard']['document']['sections'][0]['beats'][0]['visual']='先同时展示增长和消耗，再把同等长度的箭头相互抵消。';snapshot['documents']['storyboard']['version']='c'*64;job['status']='revising';return route.fulfill(status=202,json={'id':job['id']})
 if url.endswith('/approve'):
  actions.append(('approve',route.request.post_data_json));snapshot['documents']['outline']['approved']=True;snapshot['documents']['storyboard']={'document':copy.deepcopy(story),'version':'d'*64,'approved':False};snapshot['pending_stage']='storyboard';job['stage']='storyboard';return route.fulfill(status=202,json={'id':job['id']})
 if url.endswith('/planning-mode'):
  actions.append(('automatic',route.request.post_data_json));job['status']='running';return route.fulfill(status=202,json={'id':job['id']})
 return route.continue_()

with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1050})
 page.route('**/api/jobs**',route_api)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:7860');page.wait_for_load_state('networkidle')
 assert page.get_by_role('heading',name='先讲清楚，再开始制作。').is_visible()
 assert not page.get_by_role('checkbox',name='免审核，自动完成').is_checked()
 points=page.get_by_label('讲解要点（每行一条）')
 assert '\n' in points.input_value() and '\\n' not in points.input_value()
 page.get_by_label('这一章要让学生理解什么').fill('先看变化，再理解相同时间内的净消耗')
 page.get_by_role('button',name='保存草稿',exact=True).click()
 page.get_by_text('草稿已同步',exact=True).wait_for()
 assert actions[-1][0]=='save'
 page.screenshot(path=str(ART/'outline-editor.png'),full_page=True)
 page.get_by_role('button',name='确认大纲，生成分镜').click()
 page.get_by_label('老师旁白').wait_for()
 assert actions[-1][0]=='approve' and actions[-1][1]['version']=='b'*64
 page.get_by_label('修改意见',exact=True).fill('先同时画增长和消耗，再抵消。')
 page.get_by_role('button',name='AI 修改分镜').click()
 assert actions[-1][0]=='revise'
 job['status']='awaiting_review'
 page.get_by_label('画面与动画：如何证明这一步').filter(visible=True) if False else None
 page.wait_for_function("document.body.textContent.includes('草稿已同步')")
 # Reload must recover the same pending document without browser storage.
 page.reload();page.wait_for_load_state('networkidle')
 assert '同等长度' in page.get_by_label('画面与动画：如何证明这一步').input_value()
 page.screenshot(path=str(ART/'storyboard-editor.png'),full_page=True)
 for width,height in [(375,812),(812,375),(768,1024)]:
  page.set_viewport_size({'width':width,'height':height})
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),f'Overflow at {width}'
  page.screenshot(path=str(ART/f'editor-{width}.png'),full_page=True)
 page.emulate_media(reduced_motion='reduce')
 assert page.evaluate('localStorage.length===0&&sessionStorage.length===0')
 page.get_by_role('button',name='开启免审核并继续',exact=True).click()
 assert actions[-1][0]=='automatic' and actions[-1][1]['auto_approve'] is True
 assert not errors,errors
 browser.close()
print('PASS: Chromium outline edits/save/versioned approval, storyboard visual editing and AI feedback, reload recovery, explicit automatic mode, 375px mobile and landscape layouts; no page errors or browser credential storage.')
