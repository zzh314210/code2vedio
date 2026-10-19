"""Refine the actual lunar film with larger photography and causal comparison."""
import argparse,json,os,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config
from video_project import restore_credentials,write_json
from pipeline import VideoPipeline,review_summary
from execution import project_lock
from lesson_prompts import review_prompt
from media import sample_beat_frames,write_subtitles,mux,probe
p=argparse.ArgumentParser();p.add_argument('--after-pid',type=int);a=p.parse_args()
if a.after_pid:
 while True:
  try:os.kill(a.after_pid,0)
  except ProcessLookupError:break
  time.sleep(10)
project=ROOT/'video_projects/showcase-documentary-v4';out=project/'output';archive=out/'human_framing';archive.mkdir(exist_ok=True)
manifest=json.loads((out/'manifest.json').read_text());config=restore_credentials(manifest['config'],load_config(ROOT/'config.local.json'))
pipe=VideoPipeline(manifest['topic'],config,out,project=project,resume=True)
with project_lock(project):
 story=json.loads((out/'storyboard_assets.json').read_text());section=story['sections'][0];snippets=json.loads((out/'section_1_code.json').read_text());rendered=json.loads((out/'reviewed.json').read_text())
 for name in ['manifest.json','storyboard_assets.json','reviewed.json','section_1_code.json','final.mp4']:
  if not (archive/name).exists():shutil.copy2(out/name,archive/name)
 # Explicit reviewed migration; normal project resumes keep their archived helpers.
 helper=project/'code/runtime/template_components.py'
 if not (archive/'template_components.py').exists():shutil.copy2(helper,archive/'template_components.py')
 shutil.copy2(ROOT/'src/template_components.py',helper)
 pipe.config['video']['layout']='minimal'
 for index in [0,1,5]:
  code=snippets['beats'][index]['code']
  if 'framing=' not in code:code=code.replace('motion="push"','motion="push",framing="cover"')
  snippets['beats'][index]['code']=code
  section['beats'][index]['visual']='NASA真实月面照片居中裁切取景充满安全画幅，缓慢推进；标签明确原图编号，不把图解当实拍。'
 snippets['beats'][2]['code']='''label=self.scene_text('撞击如何留下坑？',font_size=34,color=self.style_color('foreground')).move_to([0,1.9,0])
self.add(label)
profile=VMobject().set_points_as_corners([[-5.5,-.7,0],[5.5,-.7,0]]).set_stroke(self.style_color('foreground'),width=4)
self.add(profile)
meteor=Circle(radius=.24,color=self.style_color('emphasis'),fill_color=self.style_color('emphasis'),fill_opacity=1).move_to([-4.7,1.3,0])
trail=Line([-5.2,1.7,0],[-4.7,1.3,0],color=self.style_color('emphasis'),stroke_width=3)
self.play(FadeIn(meteor),Create(trail),run_time=.5)
self.play(meteor.animate.move_to([0,-.7,0]),trail.animate.put_start_and_end_on([-2,.6,0],[0,-.7,0]),run_time=1.2)
crater=VMobject().set_points_smoothly([[-5.5,-.7,0],[-3,-.7,0],[-1.65,-.36,0],[-1,-1.4,0],[0,-1.75,0],[1,-1.4,0],[1.65,-.36,0],[3,-.7,0],[5.5,-.7,0]]).set_stroke(self.style_color('foreground'),width=4).set_fill(opacity=0)
self.play(FadeOut(meteor),FadeOut(trail),Transform(profile,crater),Flash([0,-.7,0],color=self.style_color('emphasis'),flash_radius=.7),run_time=.7)
particles=[];paths=[]
for sign in [-1,1]:
 for i in range(5):
  d=Dot([sign*.45,-.9,0],radius=.06,color=self.style_color('primary'));self.add(d)
  trajectory=VMobject().set_points_smoothly([[sign*.45,-.9,0],[sign*(1.1+i*.14),.7+i*.1,0],[sign*(2.6+i*.32),-.6,0]])
  particles.append(d);paths.append(MoveAlongPath(d,trajectory))
self.play(*paths,run_time=1.5)
self.play(*[FadeOut(d) for d in particles],run_time=.4)
left=self.scene_text('坑壁隆起',font_size=27,color=self.style_color('primary')).move_to([-3.8,.55,0])
arrow=Arrow([-3,.3,0],[-1.65,-.35,0],buff=.08,color=self.style_color('primary'),stroke_width=2)
right=self.scene_text('坑底下陷',font_size=27,color=self.style_color('emphasis')).move_to([3.8,.55,0])
arrow2=Arrow([3,.3,0],[.3,-1.6,0],buff=.08,color=self.style_color('emphasis'),stroke_width=2)
note=self.scene_text('过程示意 · 非按比例',font_size=20,color=self.style_color('muted')).move_to([0,-2.3,0])
self.play(FadeIn(left),Create(arrow),FadeIn(right),Create(arrow2),FadeIn(note),run_time=.8)'''
 def comparison(erode):
  return '''earth=self.scene_text('地球',font_size=39,color=self.style_color('primary')).move_to([-3.25,1.8,0])
moon=self.scene_text('月球',font_size=39,color=self.style_color('foreground')).move_to([3.25,1.8,0])
self.add(earth,moon)
line=Line([0,1.9,0],[0,-2.2,0],color=self.style_color('line'),stroke_width=1)
self.add(line)
profiles=[]
for x in [-3.25,3.25]:
 path=VMobject().set_points_smoothly([[x-2.5,-.5,0],[x-1.4,-.5,0],[x-.9,-.3,0],[x-.5,-1.1,0],[x,-1.35,0],[x+.5,-1.1,0],[x+.9,-.3,0],[x+1.4,-.5,0],[x+2.5,-.5,0]]).set_stroke(self.style_color('foreground'),width=3).set_fill(opacity=0)
 self.add(path);profiles.append(path)
''' + ('''weather=self.scene_text('风雨 · 流水',font_size=29,color=self.style_color('primary')).move_to([-3.25,.9,0])
quiet=self.scene_text('没有风雨冲刷',font_size=29,color=self.style_color('muted')).move_to([3.25,.9,0])
self.play(FadeIn(weather),FadeIn(quiet),run_time=.6)
rain=VGroup(*[Line([-5.2+i*.5,.4,0],[-5.35+i*.5,.0,0],color=self.style_color('primary'),stroke_width=2) for i in range(8)])
self.play(LaggedStart(*[FadeIn(d,shift=DOWN*.3) for d in rain],lag_ratio=.1),run_time=.8)
self.play(rain.animate.shift(DOWN*.3).set_opacity(.3),run_time=.8)
worn=VMobject().set_points_smoothly([[-5.75,-.5,0],[-4.4,-.5,0],[-3.7,-.7,0],[-3.25,-.73,0],[-2.8,-.7,0],[-2.1,-.5,0],[-.75,-.5,0]]).set_stroke(self.style_color('foreground'),width=3).set_fill(opacity=0)
self.play(Transform(profiles[0],worn),FadeOut(rain),run_time=2.2)
summary=self.scene_text('坑壁变缓，坑底逐渐填平',font_size=26,color=self.style_color('primary')).move_to([-3.25,-1.9,0])
self.play(FadeIn(summary),run_time=.5)
''' if erode else '''conditions=self.scene_paragraph('无稠密大气\\n无地表液态水',width=4.7,font_size=27,color=self.style_color('primary')).move_to([3.25,.8,0])
weather=self.scene_text('风雨和流水改写地貌',font_size=26,color=self.style_color('muted')).move_to([-3.25,.9,0])
self.play(FadeIn(conditions),FadeIn(weather),run_time=.6)
worn=VMobject().set_points_smoothly([[-5.75,-.5,0],[-4.4,-.5,0],[-3.7,-.7,0],[-3.25,-.73,0],[-2.8,-.7,0],[-2.1,-.5,0],[-.75,-.5,0]]).set_stroke(self.style_color('foreground'),width=3).set_fill(opacity=0)
self.remove(profiles[0]);self.add(worn)
axis=Arrow([1,-2,0],[5.4,-2,0],buff=0,color=self.style_color('primary'),stroke_width=2)
self.play(Create(axis),Indicate(profiles[1],scale_factor=1.01,color=self.style_color('primary')),run_time=1.6)
summary=self.scene_text('时间流逝，撞击痕迹长久保留',font_size=24,color=self.style_color('primary')).move_to([3.25,-2.4,0])
self.play(FadeIn(summary),run_time=.5)
''')
 snippets['beats'][3]['code']=comparison(True);snippets['beats'][4]['code']=comparison(False)
 section['beats'][2]['visual']='动画剖面示意：陨石撞击、碎屑抛射、坑壁隆起与坑底下陷，明确非按比例。'
 section['beats'][3]['visual']='同屏标记地球与月球，地球侧风雨侵蚀使坑壁变缓，月球侧形状保留。'
 section['beats'][4]['visual']='延续同一左右位置，地球浅坑对比月球清晰坑形，解释缺少风雨侵蚀使痕迹长期保留。'
 pipe.validate_snippets(snippets,len(section['beats']));rev=max(int(x.name.split('_')[-1]) for x in (out/'section_1').glob('revision_*'))+1
 write_json(archive/'code.json',snippets);write_json(archive/'storyboard.json',story)
 print('Rendering documentary framing refinement',rev,flush=True);video=pipe.render(section,snippets,rev)
 frames=sample_beat_frames(video,archive/f'review_{rev}',section['beats'],12)
 timestamps=json.loads((frames[0].parent/'timestamps.json').read_text())
 pipe.active_stage='review';review=pipe.vision.json(pipe.prompt('review',review_prompt(section,pipe.templates,frame_timestamps=timestamps)),pipe.validate_feedback,images=frames);review['reviewed_revision']=rev
 write_json(archive/f'review_{rev}.json',review);print(json.dumps(review,ensure_ascii=False),flush=True)
 if review['has_issues']:raise RuntimeError('Refined documentary requires further review; original film preserved')
 rendered['section_1']={'video':str(video),'revision':rev}
 write_json(out/'section_1_review_99.json',review);write_json(out/'section_1_code.json',snippets);write_json(out/'storyboard_assets.json',story);write_json(out/'reviewed.json',rendered)
 duration=write_subtitles(section['beats'],out/'subtitles.srt');mux(video,out/'narration.wav',out/'subtitles.srt',out/'final.mp4',duration)
 manifest.update(status='complete',media=probe(out/'final.mp4'),visual_review=review_summary(out,rendered,True),human_refinement='Cinematic image crop and minimal chrome; explicit helper migration; larger labeled impact diagram; consistent Earth/Moon erosion comparison')
 write_json(out/'manifest.json',manifest);write_json(out/'review_status.json',manifest['visual_review']);write_json(out/'timeline.json',section['beats'])
 write_json(project/'showcase_receipt.json',{'template':'documentary','result':str(out/'final.mp4'),'status':'generated','human_review':'pending after framing refinement'})
 print('Documentary refined; inspect actual film before publishing.',flush=True)
