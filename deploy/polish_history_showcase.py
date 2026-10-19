"""Refine a real history film's ending; preserve originals and re-review changes."""
import argparse,json,math,os,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config
from video_project import restore_credentials,write_json
from pipeline import VideoPipeline,review_summary
from execution import project_lock
from lesson_prompts import review_prompt
from media import sample_beat_frames,fit_audio,concat,write_subtitles,mux,probe
p=argparse.ArgumentParser();p.add_argument('--after-pid',type=int);p.add_argument('--reuse-render',type=int);a=p.parse_args()
if a.after_pid:
 while True:
  try:os.kill(a.after_pid,0)
  except ProcessLookupError:break
  time.sleep(10)
project=ROOT/'video_projects/showcase-history_map-v4';out=project/'output';archive=out/'human_ending';archive.mkdir(exist_ok=True)
manifest=json.loads((out/'manifest.json').read_text());config=restore_credentials(manifest['config'],load_config(ROOT/'config.local.json'))
pipe=VideoPipeline(manifest['topic'],config,out,project=project,resume=True)
with project_lock(project):
 storyboard=json.loads((out/'storyboard_assets.json').read_text());rendered=json.loads((out/'reviewed.json').read_text())
 for name in ['manifest.json','storyboard_assets.json','reviewed.json','section_2_code.json','final.mp4']:
  if (out/name).is_file() and not (archive/name).exists():shutil.copy2(out/name,archive/name)
 section=storyboard['sections'][1]
 section['beats']=[
  {'narration':'巴黎外交失败是导火索，北京学生抗议是起点，上海工人加入使运动扩大。这场运动促进了马克思主义传播。','caption':'导火索—起点—扩大—影响','visual':'四个独立考点卡，按顺序出现，不重复播放地图。','duration_seconds':13},
  {'narration':'想一想：起点和扩大，分别在哪座城市？','caption':'先自己回答，再看下一幕','visual':'只显示问题，不提前揭示答案。','duration_seconds':7,'hold_after_seconds':2},
  {'narration':'起点在北京，扩大到上海。用地点串起事件，记得更牢。','caption':'北京起点，上海扩大','visual':'保留同一问题，下方清晰显示答案。','duration_seconds':8.5}]
 pipe.prepare_audio(section)
 remaining=90-sum(b['duration'] for b in storyboard['sections'][0]['beats']);spoken=sum(b['duration'] for b in section['beats'])
 if spoken>remaining:raise RuntimeError(f'Ending speech {spoken:.2f}s exceeds {remaining:.2f}s; never truncate')
 slack=remaining-spoken
 for beat in section['beats']:beat['duration']+=math.floor(slack*beat['duration_seconds']/28.5*30)/30
 section['beats'][-1]['duration']+=remaining-sum(b['duration'] for b in section['beats'])
 code=''
 for i,(title,fact) in enumerate([('导火索','巴黎和会：中国外交失败'),('起点','5月4日：北京学生抗议'),('扩大','6月：上海工人加入'),('影响','促进马克思主义传播')]):
  x=(-3 if i%2==0 else 3);y=1.1-(i//2)*2.1
  code+=f"box{i}=RoundedRectangle(width=5.25,height=1.7,corner_radius=.12,color=self.style_color('line'),stroke_width=1.4).move_to([{x},{y},0])\n"
  code+=f"head{i}=self.scene_text({title!r},font_size=28,color=self.style_color('primary')).move_to([{x},{y+.48},0])\n"
  code+=f"body{i}=self.scene_paragraph({fact!r},width=4.65,font_size=29,color=self.style_color('foreground')).move_to([{x},{y-.22},0])\n"
  code+=f"self.play(FadeIn(box{i}),FadeIn(head{i}),FadeIn(body{i}),run_time=.7)\n"
 question="q=self.scene_paragraph('起点和扩大，分别在哪座城市？',width=10,font_size=38,color=self.style_color('foreground')).move_to([0,.8,0])\nself.play(FadeIn(q),run_time=.5)\n"
 ask=question+"hint=self.scene_text('先自己回答，再看下一幕',font_size=28,color=self.style_color('primary')).move_to([0,-.8,0])\nself.play(FadeIn(hint),run_time=.5)\n"
 answer=question+"a=self.scene_text('起点在北京，扩大到上海',font_size=38,color=self.style_color('emphasis')).move_to([0,-.8,0])\nself.play(FadeIn(a),run_time=.6)\n"
 snippets={'beats':[{'code':x} for x in [code,ask,answer]]}
 pipe.validate_snippets(snippets,3);rev=a.reuse_render if a.reuse_render is not None else max(int(x.name.split('_')[-1]) for x in (out/'section_2').glob('revision_*'))+1
 write_json(archive/'ending.json',section);write_json(archive/'code.json',snippets)
 if a.reuse_render is None:
  print('Rendering refined ending',rev,flush=True);video=pipe.render(section,snippets,rev)
 else:
  directory=out/'section_2'/f'revision_{rev}'
  if (directory/'scene.py').read_text()!=pipe.assemble_code(section,snippets):raise RuntimeError('Existing render does not match the current ending; refusing reuse')
  candidates=list((directory/'media').rglob('lesson.mp4'))
  if len(candidates)!=1:raise RuntimeError('No unique completed ending render')
  video=candidates[0];print('Reusing unchanged rendered ending with timestamp-aware review',rev,flush=True)
 frames=sample_beat_frames(video,archive/f'review_{rev}',section['beats'],12)
 timestamps=json.loads((frames[0].parent/'timestamps.json').read_text())
 pipe.active_stage='review';review=pipe.vision.json(pipe.prompt('review',review_prompt(section,pipe.templates,frame_timestamps=timestamps)),pipe.validate_feedback,images=frames);review['reviewed_revision']=rev
 write_json(archive/f'review_{rev}{"_timed" if a.reuse_render is not None else ""}.json',review);print(json.dumps(review,ensure_ascii=False),flush=True)
 if review['has_issues']:raise RuntimeError('Refined ending needs another review; previous film preserved')
 rendered['section_2']={'video':str(video),'revision':rev}
 write_json(out/'section_2_review_99.json',review);write_json(out/'section_2_code.json',snippets);write_json(out/'storyboard_assets.json',storyboard);write_json(out/'reviewed.json',rendered)
 beats=[];videos=[];audios=[]
 for part in storyboard['sections']:
  videos.append(Path(rendered[part['id']]['video']))
  for i,beat in enumerate(part['beats']):
   destination=archive/f"{part['id']}-{i}.wav";fit_audio(Path(beat['audio']),destination,beat['duration']);audios.append(destination);beats.append(beat)
 concat(videos,archive/'animation.mp4');concat(audios,archive/'narration.wav',audio=True);duration=write_subtitles(beats,out/'subtitles.srt')
 mux(archive/'animation.mp4',archive/'narration.wav',out/'subtitles.srt',out/'final.mp4',duration)
 manifest.update(status='complete',media=probe(out/'final.mp4'),visual_review=review_summary(out,rendered,True),human_refinement='Four fact summary; separate question and answer with actual two-second recall pause')
 write_json(out/'manifest.json',manifest);write_json(out/'review_status.json',manifest['visual_review']);write_json(out/'timeline.json',beats)
 write_json(project/'showcase_receipt.json',{'template':'history_map','result':str(out/'final.mp4'),'status':'generated','human_review':'pending after ending refinement'})
 print('History ending refined; inspect final film before publishing.',flush=True)
