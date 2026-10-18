"""Cross-topic style isolation, offline handdrawn paths, and actual Manim rendering.
No LLM/TTS/vision API requests. Hand-authored probe scenes test renderer capability,
not the teaching quality of model-generated lessons.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from configuration import ROOT, DEFAULTS, merge, resolve_config
from pipeline import VideoPipeline, validate_code, validate_video_constraints
from styles import load_style
from handdrawn_runtime import _paths

STYLES = ('studio_noir', 'studio_editorial', 'studio_sketch')
TOPICS = {
    'compound': ('复利：增长会加速', '曲线的高度表示累计金额', '''
axes = VGroup(self.sketch_shape("arrow", points=[[-4,-1.8],[4,-1.8]]), self.sketch_shape("arrow", points=[[-4,-1.8],[-4,1.7]]))
points = [[-3.8+i*.35, -1.6+.19*((1.16**i)-1)] for i in range(21)]
curve = self.sketch_shape("curve", points=points, color=self.style_color("emphasis"))
label = self.scene_text("相同利率，收益逐期累积", 27).move_to([.6,1.9,0])
self.play(Create(axes), Create(curve), FadeIn(label), run_time=.7)
'''),
    'circuit': ('电路：闭合后电流流通', '连接关系由当前课题动态生成', '''
points = [[-3,-1.3],[-3,1.2],[3,1.2],[3,-1.3],[-3,-1.3]]
wires = VGroup(*[self.sketch_shape("line", points=[a,b]) for a,b in zip(points,points[1:])])
source = self.sketch_shape("ellipse", width=1, height=1, center=[-3,0,0], fill=self.style_color("panel"))
bulb = self.sketch_shape("ellipse", width=1, height=1, center=[3,0,0], color=self.style_color("emphasis"), fill=self.style_color("panel"))
flow = self.sketch_shape("arrow", points=[[-1,.7],[1,.7]], color=self.style_color("secondary"))
self.play(Create(wires), FadeIn(source), FadeIn(bulb), Create(flow), run_time=.7)
'''),
    'network': ('网络：一个节点连接多个节点', '节点数量和连线均可自由变化', '''
locations = [[-3,1],[3,1],[-3,-1.2],[3,-1.2]]
links = VGroup(*[self.sketch_shape("arrow", points=[[0,0],p], color=self.style_color("muted")) for p in locations])
nodes = VGroup(*[self.sketch_shape("ellipse", width=1.1, height=.8, center=[p[0],p[1],0], fill=self.style_color("panel")) for p in locations])
hub = self.sketch_shape("rectangle", width=1.6, height=.9, fill=self.style_color("panel"))
ink = self.ink_path([[-1,-2],[-.5,-1.85],[0,-2],[.5,-1.85],[1,-2]], color=self.style_color("emphasis"))
self.play(Create(links), FadeIn(nodes), FadeIn(hub), Create(ink), run_time=.7)
'''),
}


def config(style, task=None):
    return resolve_config(merge(DEFAULTS, {'style':style, 'text':{'api_key':'test-not-used','model':'test-model'},
        'vision':{'enabled':False}, 'tts':{'provider':'none'}, 'assets':{'enabled':False},
        'video':{'quality':'low','fps':12}, 'video_overrides':{'quality':'low','fps':12}, 'task':task or {}}))


def check():
    forbidden = ('六面体','公共边','cube_lesson','原图E','原图D','空间推理','蓝色代表E')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for style in STYLES:
            for topic, (title, caption, code) in TOPICS.items():
                project = root / (style+'-'+topic)
                pipe = VideoPipeline(title,config(style),project/'output',project=project)
                assert not pipe.extensions
                assert not (project/'code/runtime/cube_geometry.py').exists()
                assert not (project/'code/runtime/studio_components.py').exists()
                assert (project/'code/runtime/vendor/handdrawn/rough.cjs').is_file()
                assert (project/'code/runtime/vendor/handdrawn/perfect-freehand.cjs').is_file()
                for stage in ('outline','storyboard','code','review'):
                    prompt = pipe.prompt(stage, 'current task')
                    assert all(word not in prompt for word in forbidden), (style,stage)
                validate_code({'beats':[{'code':code}]}, 1, pipe.extensions, pipe.config['video'])
                for bad in ('self.add(Circle(color=RED))', 'self.add(Circle(color="#FF00FF"))',
                            'self.add(Text("drift", font="Arial"))', 'self.scene_text("drift",30,"red")', 'self.add(Circle(color="red"))',
                            'self.extension("cube_lesson", stage=0)'):
                    try:validate_code({'beats':[{'code':bad}]},1,pipe.extensions,pipe.config['video'])
                    except ValueError:pass
                    else:raise AssertionError('Accepted style or content drift: '+bad)
        project=root/'explicit-baseline'
        pipe=VideoPipeline('baseline',config('studio_sketch',{'component_profile':'cube_baseline'}),project/'output',project=project)
        assert 'cube_lesson' in pipe.extensions
    payload=json.dumps({'kind':'ink','points':[[0,0],[40,20],[80,0]],'size':5,'simulatePressure':True})
    assert len(_paths(payload)['outline'])>3
    print('PASS: 9 topic/style combinations are independent of baseline content; arbitrary graphics accepted, palette/font drift rejected; explicit baseline opt-in works; real offline library executes.')


def render_previews():
    from media import run_command, ffmpeg_binary
    from PIL import Image, ImageOps, ImageDraw
    output=ROOT/'deliverables/style-consistency'
    output.mkdir(parents=True,exist_ok=True)
    work=ROOT/'.tmp/series-style-previews'
    work.mkdir(parents=True,exist_ok=True)
    records=[]
    for style in STYLES:
        for topic,(title,caption,code) in TOPICS.items():
            project=Path(tempfile.mkdtemp(prefix=style+'-'+topic+'-',dir=work))
            pipe=VideoPipeline(title,config(style),project/'output',project=project)
            section={'id':'section_1','title':title,'assets':[], 'beats':[{'duration':1.4,'caption':caption,'narration':'Probe only','subtitles':[]}]}
            video=pipe.render(section,{'beats':[{'code':code}]},0)
            image=output/(style+'-'+topic+'.png')
            run_command([ffmpeg_binary(),'-y','-ss','1','-i',str(video),'-frames:v','1',str(image)])
            records.append({'style':style,'topic':topic,'image':image.name,'project':str(project.relative_to(ROOT))})
            print('Rendered '+style+' / '+topic,flush=True)
    canvas=Image.new('RGB',(1440,810),'#e7e7e7')
    for index,record in enumerate(records):
        with Image.open(output/record['image']) as source:
            canvas.paste(source.resize((480,270)),((index%3)*480,(index//3)*270))
    canvas.save(output/'contact-sheet.jpg',quality=93)
    (output/'report.json').write_text(json.dumps({'scope':'Actual offline renderer probes using hand-authored scenes; no generative-model or production-quality claim.','rows':list(STYLES),'columns':list(TOPICS),'previews':records},ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS: nine actual Manim renders and contact sheet saved to '+str(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--render',action='store_true');args=parser.parse_args()
    check()
    if args.render:render_previews()
