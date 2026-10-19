"""Small fixed editorial contracts layered over the existing Code2Video pipeline."""
import copy
import json
from pathlib import Path
CATALOG=json.loads((Path(__file__).resolve().parents[1]/'templates/catalog.json').read_text())

def apply_template(config,identity):
    if not identity:return config
    template=next((t for t in CATALOG if t['id']==identity),None)
    if not template:raise ValueError('请选择可用的创作模板。')
    result=copy.deepcopy(config)
    task=copy.deepcopy(result.get('task') or result.get('course') or {})
    task['instructions']='\n'.join(filter(None,[task.get('instructions',''),template['direction']]))
    task['template_id']=identity
    task['template_version']=5
    prompts=task.setdefault('prompts',{})
    direction={'explainer':'科普动画必须先核对几何因果：光线箭头、被照亮的一侧、观察位置必须一致。月相使用lunar_phases组件，它同时呈现太空俯视和地球所见，标明北半球常见方向。其他物理主题也必须区分示意和实拍，并核对箭头方向、运动和结果。','math_visual':'讲多项式割线、切线、导数时优先用function_plot：coefficients按常数项到高次项排列，例如x平方为[0,0,1]。focus是固定点横坐标，offsets是非零横向间隔列表，所有点必须在x_range和y_range内。mode=tangent会显示割线逐步趋向真正切线，数值和图形由组件精确计算。公式推导另占一个beat使用formula_steps，不能把长公式与图形挤在同一屏。非多项式、其他数学题材正常画图，但曲线必须截断在坐标框内，不能进入标题或字幕区。','word_story':'故事镜头优先使用 story_scene 内置可辨认角色（banana/robot/cat）和动作（sail/leave/arrive/discover）；用同一个角色、道具和目的地保持连续性，不能用普通圆点或胶囊冒充香蕉或船。例句和回忆镜头使用 vocabulary_card，避免词义、例句和背景单词叠在一起。同一beat只调用一个组件，不叠加其他文字或图形。', 'product':'当有图片素材时必须使用授权素材作为画面主体，用 self.extension("media_shot", key=实际素材key, label=短标签, motion="push") 展示真实产品，不用简单方块代替实际外观。每个beat只调用一次展示，不再额外叠加标签。','documentary':'真实照片用 media_shot 的 framing=cover 做充满安全画幅的电影式取景，关键内容不能因裁切丢失；通过不同素材形成连贯叙事。图解镜头只解释必要机制，主体居中占足画面；比较两种情况必须同屏显示并用短标签区分。不用一串小图居中加大块空白。','history_map':'必须使用 map_story 扩展绘制真实坐标的地图。每个地点准确给出经纬度，巴黎48.86,2.35，北京39.90,116.41，上海31.23,121.47；地图列表跨镜头保持一致，active随事件变化。该组件占用整片安全画布；同一beat只调用该组件，不得再增加任何日期、标题、说明、箭头或移动组件。用date参数传入日期（最多14字），event传入关键事件（最多26字），组件统一排版。总结镜头可以不用地图，另用简洁因果链。','notes':'开场、转折与结尾使用 knowledge_map 展示同一组3至5个核心节点，通过active高亮当前节点。中间解释使用图形演示，不仅是文字卡片。若笔记讲多项式导数，可用function_plot展示真实割线与切线变化；coefficients按幂次从低到高。所有曲线限制在坐标框内，不能越进标题和字幕区。'}
    if identity in direction:
        canvas_rule='完整画布组件的硬约束：同一beat最多调用一次self.extension；调用后只可self.wait，不得再self.add/play、绘制文字、边框、箭头或对返回对象做变换。组件自己完成动画与排版，标签通过参数传入。不使用组件的独立beat可以用普通Manim绘制。'
        prompts['code']='\n'.join(filter(None,[prompts.get('code',''),direction[identity],canvas_rule]))
        prompts['storyboard']='\n'.join(filter(None,[prompts.get('storyboard',''),direction[identity], '设计镜头时遵守组件边界：地图、素材照片、知识地图、故事角色、词义回忆各自占一个独立beat；不要在同一镜头规划多个组件或额外叠加文字、局部圈注、小窗。标题、字幕、来源由框架展示。照片镜头一次展示一张照片并慢推近；产品素材必须完整保留，纪录片可裁切取景。图形解释另外安排镜头。']))
    if identity in {'history_map','notes','math_visual','word_story'}:
        for stage in ['storyboard','code']:
            prompts[stage]=prompts.get(stage,'')+'\n总结用review_cards归纳2至4个短考点，不重复播放地图。回忆题先提问一个可从本片得到明确答案的问题，单独提问beat设置hold_after_seconds=2，再用下一个beat揭晓；用recall_card，提问reveal=False，答案reveal=True。不要用未经讲解的反事实假设题收尾。'
    if identity in {'history_map','notes','math_visual','word_story'}:
        prompts['storyboard']=prompts.get('storyboard','')+'\n必须预留最后两个beats作为提问和答案，分别增加recall_role字段question和answer。提问beat的hold_after_seconds至少2秒，答案必须能从本片内容直接得到。不要用完所有beats后遗漏答案。'
    if identity=='notes':
        prompts['storyboard']+='\n严格核对笔记和用户要求的小测数量。若承诺三道小测，最后一章必须是六个beats：问题1、答案1、问题2、答案2、问题3、答案3；每题先停顿2秒。章节标题不能承诺不存在的内容。中间长段概念拆成独立可视化镜头，每幕只讲一个易混点。'
    if identity=='word_story':
        prompts['storyboard']+='\n总计最多6个镜头：两个故事动作镜头、词义揭晓（同时说明只是记忆联想不是词源）、常用例句、回忆提问、答案。不要单独占用一个镜头声明不是词源。'
    if identity=='documentary':result.setdefault('video',{})['layout']='minimal'
    result['task']=task;result['course']=task
    return result
