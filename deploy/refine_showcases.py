"""Apply actual-film review findings in a NEW pipeline project.

Original model-generated projects stay untouched. New helper snapshots, revised
storyboards, actual TTS, Docker rendering, fresh model review and muxing all run
through the normal Code2Video pipeline. Publishing is a separate human decision.
"""
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config,sanitize_error
from video_templates import CATALOG,apply_template
from pipeline import VideoPipeline
from video_project import write_json
p=argparse.ArgumentParser();p.add_argument('template',choices=['math_visual','explainer','documentary','product','notes']);p.add_argument('--revision',default='v7');p.add_argument('--resume',action='store_true');a=p.parse_args()
t=next(t for t in CATALOG if t['id']==a.template)
previous={'math_visual':'v6','explainer':'v4','documentary':'v4','product':'v5','notes':'v5'}[a.template]
source=ROOT/'video_projects'/f'showcase-{a.template}-{previous}'
project=ROOT/'video_projects'/f'showcase-{a.template}-{a.revision}'
assert source!=project,'Never modify the original example'
def extension(name,**values):return {'code':f'self.extension({name!r}'+''.join(f', {k}={v!r}' for k,v in values.items())+')'}
def beat(narration,caption,visual,weight=10,**kw):return {'narration':narration,'caption':caption,'visual':visual,'duration_seconds':weight,**kw}
config=load_config(ROOT/'config.local.json',overrides={'text':{'model':'kimi-k3','fallback_models':['deepseek-v4.1-flash-1017']},'vision':{'model':'deepseek-v4.1-flash','fallback_models':['qwen3.8-flash'],'enabled':True,'inherit_text':False,'frames':12,'rounds':2,'require_pass':True},'tts':{'provider':'edge','voice':'zh-CN-YunxiNeural'},'style':t['style'],'video':{'quality':'high','fps':30,'target_duration':t['duration'],'max_sections':3 if a.template=='notes' else 1,'max_beats':6,'render_timeout':900,'pause_seconds':.15},'assets':{'enabled':False,'max_per_section':6},'teaching_research':{'enabled':False}})
config=apply_template(config,t['id'])
# Explicit overrides survive the style package merge.
config.setdefault('video_overrides',{})['brand']=''
if a.template=='documentary':config['video_overrides']['layout']='minimal'
def event(value):print(json.dumps(value,ensure_ascii=False),flush=True)
try:
 pipe=VideoPipeline(t['example_prompt'],config,project/'output',project=project,materials=[ROOT/x for x in t.get('example_materials',[])],resume=a.resume,on_event=event)
 if not a.resume:
  outline=json.loads((source/'output/outline.json').read_text())
  story=json.loads((source/'output/storyboard.json').read_text())
  snippets={s['id']:json.loads((source/'output'/f"{s['id']}_code.json").read_text()) for s in story['sections']}
  section=story['sections'][0]
  if a.template=='math_visual':
   snippets['section_1']={'beats':[
    extension('function_plot',offsets=[1],label='y=x²：A=(1,1)，B沿曲线移动'),
    extension('function_plot',offsets=[1,.5,.1],label='间隔变小，割线逐渐靠近切线'),
    extension('formula_steps',lines=['((1 + h)² − 1) / h','= (1 + 2h + h² − 1) / h','= (2h + h²) / h','= 2 + h'],title='平均变化率 = 纵差 ÷ 横差',note='h ≠ 0，才能约去 h'),
    extension('function_plot',offsets=[.1,.01],mode='tangent',label='x=1：切线斜率就是导数'),
    extension('recall_card',question='y=x² 在 x=1 处，切线斜率是多少？'),
    extension('recall_card',question='y=x² 在 x=1 处，切线斜率是多少？',answer='2，因为 2+h 在 h→0 时趋近于 2',reveal=True)]}
   for i,b in enumerate(section['beats']):
    b['visual']=['精确曲线和割线组件，A和B分别清楚标记，全部内容在安全区域。','同一曲线和坐标，B随h从1到0.5到0.1连续移动，斜率3到2.5到2.1。','独立推导画面：逐行化简平均变化率，明确h不等于0，不叠加曲线。','同一坐标内连续逼近真正切线，数值2准确；曲线不越界。','只提问，留出真实2秒停顿。','明确给出2和极限理由。'][i]
  elif a.template=='explainer':
   stages=['orbit','half','orbit','new','first_quarter','summary']
   snippets['section_1']={'beats':[extension('lunar_phases',stage=s) for s in stages]}
   for b,stage in zip(section['beats'],stages):b['visual']='使用lunar_phases组件，阶段 '+stage+'。太阳光始终从右向左，太空俯视里月球右半朝向太阳；地球所见亮面按真实投影变化，标注北半球常见观察方向与非按比例。总结明确区分月相与月食。'
  elif a.template=='documentary':
   section['title']=outline['sections'][0]['title']='月球的伤痕'
   for i in [0,1,5]:
    code=snippets['section_1']['beats'][i]['code']
    if 'framing=' not in code:code=code.replace('motion="push"','motion="push",framing="cover"')
    snippets['section_1']['beats'][i]['code']=code
    section['beats'][i]['visual']='真实NASA照片缓慢推进，图片来源标签完整置于字幕区域上方；主体充足，照片与过程图解明确区分。'
   # Prior manual refinement is itself audited; use its causal diagrams.
   prior=source/'output/human_framing/code.json'
   if prior.is_file():
    fixed=json.loads(prior.read_text())
    for i in [2,3,4]:snippets['section_1']['beats'][i]=fixed['beats'][i]
   section['beats'][2]['visual']='明确标记非按比例的撞击剖面图解：陨石撞击、物质抛射、坑壁隆起与坑底下陷。'
   section['beats'][3]['visual']='地球左、月球右。同屏对比，风雨使地球坑壁变缓，月球坑形保留。'
   section['beats'][4]['visual']='延续地球左月球右的对比：月球缺少稠密大气和地表液态水，古老撞击坑保留。'
  elif a.template=='product':
   section['title']=outline['sections'][0]['title']='从想法到画面：准备好你的创作'
   labels=['从一个视频想法开始','第一步：描述你的视频想法','第二步：选择合适的视觉风格','第三步：查看预览与参数','先填写想法，生成时再登录']
   snippets['section_1']={'beats':[extension('media_shot',key='reference_image_'+str(i),label=label,motion='push') for i,label in zip([0,0,1,2,0],labels)]}
   for b,label in zip(section['beats'],labels):b['visual']='完整展示当前公开访客网站截图，克制推近。独立短标签：'+label+'。只是创作准备演示，不宣称完成三个操作就已产生成片。'
  else:
   nodes=['变化率','导数例子','符号与极值','易混对照']
   sections=[
    ('沿着知识地图，理解导数',[
     beat('今天的笔记沿四个节点串起来：变化率、导数例子、符号与极值，最后辨清易混点。先看两点之间，再看一个点。','把笔记串成一张知识地图','同一组四节点知识地图，当前高亮变化率。',12),
     beat('看平方函数。固定点A在一逗号一，B在二逗号四。纵差三，横差一，割线斜率就是三。','平均变化率：纵差 ÷ 横差','function_plot精确画A、B和割线，h=1，割线斜率3。',11),
     beat('让B靠近A，割线越来越贴近切线。斜率趋近二，这就是A点处的导数。趋近零，可不是直接除以零。','从平均变化率，走向瞬时变化率','function_plot连续移动B，割线转动，最终切线斜率2。',12),
     beat('用式子再看一遍：一加h的平方减一，再除以h，化简成二加h。h不等于零，才可以约分。','每一步，都有条件','formula_steps分步展示三行化简，明确h不等于0。',12),
     beat('换到x等于二，切线斜率变成四。不同位置，变化快慢也不同。导数回答的是此刻变化多快。','x=2：导数为4','function_plot focus2，精确斜率4，固定坐标内展示。',9),
     beat('现在回到地图：我们已经把割线、切线和具体算例连上了，接着用导数的符号判断函数怎么变。','回到地图，进入下一节点','同一知识地图，当前高亮符号与极值。',9)
    ]),
    ('看符号，辨极值，分清易混点',[
     beat('在一个区间里，导数始终为正，函数就严格递增。看这条向右上升的直线，斜率是一。','区间内导数始终正：严格递增','精确一次函数y=x的切线，斜率1，可见随x上升。',10),
     beat('导数始终为负，就严格递减。这条向右下降的直线，斜率是负一。注意判断的是整个区间。','区间内导数始终负：严格递减','精确一次函数y=-x的切线，斜率-1。',10),
     beat('单点导数为零，不一定有极值。看立方函数：原点的切线水平，曲线却继续从左下走向右上。','反例：y=x³ 在0处没有极值','精确立方曲线与原点水平切线，左右仍连续上升。',12),
     beat('看两侧变号：从正到负，先升后降，是局部极大；从负到正，先降后升，是局部极小。','两侧变号，才看得出转折','两张短对照卡，正到负对应极大，负到正对应极小。',12),
     beat('别把高度当速度。函数值看位置多高，导数看变化多快。也别混淆两点间的平均变化，和一点处的瞬时变化。','多高与多快，区间与一点','四张短对照卡，分别解释函数值、导数、割线、切线。',12),
     beat('把笔记串回地图：变化率引出导数，导数符号描述单调性，再用变号检查极值。接下来，合上笔记试三道题。','用一条链，串起四个节点','同一组知识地图，当前高亮易混对照。',10)
    ]),
    ('三道回忆小测',[
     beat('第一题，平方函数在x等于一处，导数是多少？','第一题：y=x² 在x=1处的导数','recall_card先提问，停顿2秒。',6,recall_role='question',hold_after_seconds=2),
     beat('答案是二。割线斜率二加h，在h趋近零时趋近二。','答案一：2','recall_card显示答案与简短理由。',6,recall_role='answer'),
     beat('第二题，某点导数为零，一定有极值吗？','第二题：导数为0，一定有极值吗','recall_card先提问，停顿2秒。',6,recall_role='question',hold_after_seconds=2),
     beat('不一定。立方函数在原点导数为零，却仍然递增。','答案二：不一定','recall_card显示准确反例。',6,recall_role='answer'),
     beat('第三题，区间内导数始终为负，函数怎么变？','第三题：区间内导数始终负','recall_card先提问，停顿2秒。',6,recall_role='question',hold_after_seconds=2),
     beat('严格递减。记住这条线索：看图理解变化，再用导数解释变化。','答案三：严格递减','recall_card显示答案和回顾线索。',7,recall_role='answer')
    ])]
   story={'sections':[{'id':f'section_{i+1}','title':title,'beats':beats} for i,(title,beats) in enumerate(sections)]}
   for s,(title,_) in zip(outline['sections'],sections):s['title']=title
   snippets={
    'section_1':{'beats':[extension('knowledge_map',items=nodes,active=0),extension('function_plot',offsets=[1],label='y=x²：两点之间的平均变化率'),extension('function_plot',mode='tangent',label='y=x²：x=1处的瞬时变化'),extension('formula_steps',lines=['((1 + h)² − 1) / h','= (2h + h²) / h','= 2 + h'],title='从图形走到式子',note='h ≠ 0，才可以约分'),extension('function_plot',focus=2,offsets=[.5,.1],mode='tangent',x_range=[-.3,3],y_range=[-.5,9],label='y=x²：x=2处斜率为4'),extension('knowledge_map',items=nodes,active=2)]},
    'section_2':{'beats':[extension('function_plot',coefficients=[0,1],focus=0,offsets=[1,.5],mode='tangent',x_range=[-2,2],y_range=[-2,2],label='y=x：向右走，函数值上升'),extension('function_plot',coefficients=[0,-1],focus=0,offsets=[1,.5],mode='tangent',x_range=[-2,2],y_range=[-2,2],label='y=−x：向右走，函数值下降'),extension('function_plot',coefficients=[0,0,0,1],focus=0,offsets=[1,.5,.1],mode='tangent',x_range=[-1.5,1.5],y_range=[-3.5,3.5],label='y=x³：水平切线，不代表极值'),extension('review_cards',items=[{'title':'正 → 负','text':'先升后降：局部极大'},{'title':'负 → 正','text':'先降后升：局部极小'}]),extension('review_cards',items=[{'title':'函数值','text':'当前位置有多高'},{'title':'导数','text':'此刻变化有多快'},{'title':'割线','text':'两点之间：平均变化率'},{'title':'切线','text':'一个点处：瞬时变化率'}]),extension('knowledge_map',items=nodes,active=3)]},
    'section_3':{'beats':sum(([extension('recall_card',question=q),extension('recall_card',question=q,answer=ans,reveal=True)] for q,ans in [('y=x² 在x=1处，导数是多少？','2；因为 2+h 在h→0时趋近于2'),('导数为0，一定有极值吗？','不一定；y=x³ 在0处仍递增'),('区间内导数始终为负，函数怎么变？','在该区间严格递减')]),[])}
   }
  pipe.validate_outline(outline);pipe.validate_storyboard(story,outline)
  write_json(pipe.output/'outline.json',outline);write_json(pipe.output/'storyboard.json',story)
  for s in story['sections']:
   pipe.validate_snippets(snippets[s['id']],len(s['beats']));write_json(pipe.output/f"{s['id']}_code.json",snippets[s['id']])
  write_json(project/'manual_refinement.json',{'source':source.name,'reason':'Actual-film inspection found factual/layout/pedagogical issues; new helper snapshots and revised shots, original retained','template':a.template})
 result=pipe.run()
 write_json(project/'showcase_receipt.json',{'template':a.template,'result':str(result),'status':'generated','human_review':'pending; this is a manually refined model-generated film'})
 print('REFINEMENT GENERATED; inspect before publication:',str(result),flush=True)
except Exception as error:
 print('REFINEMENT INCOMPLETE:',sanitize_error(str(error),config)[:1800],flush=True);raise
