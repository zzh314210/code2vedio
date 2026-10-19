"""Keep real model-generated story; refine collocations and reveal recall answer."""
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
project=ROOT/'video_projects/showcase-word_story-v4';out=project/'output';archive=out/'human_recall';archive.mkdir(exist_ok=True)
manifest=json.loads((out/'manifest.json').read_text());config=restore_credentials(manifest['config'],load_config(ROOT/'config.local.json'))
pipe=VideoPipeline(manifest['topic'],config,out,project=project,resume=True)
with project_lock(project):
 story=json.loads((out/'storyboard_assets.json').read_text());section=story['sections'][0];snippets=json.loads((out/'section_1_code.json').read_text());rendered=json.loads((out/'reviewed.json').read_text())
 for name in ['manifest.json','storyboard_assets.json','reviewed.json','section_1_code.json','final.mp4']:
  if not (archive/name).exists():shutil.copy2(out/name,archive/name)
 snippets['beats'][4]['code']='self.extension("vocabulary_card",word="abandon",meaning="放弃、抛弃",example="The captain had to abandon the boat.\\nabandon a plan = 放弃计划",quiz=False)'
 beat=section['beats'][-1];reveal=max(cue['end'] for cue in beat['subtitles'])+2
 if beat['duration']<reveal+1.8:raise RuntimeError('Not enough time for a genuine recall pause and readable answer')
 snippets['beats'][-1]['code']=f'''label=self.scene_text('先回忆，再揭晓',font_size=27,color=self.style_color('primary')).move_to([0,1.8,0])
q=self.scene_text('abandon 是什么意思？',font_size=45,color=self.style_color('foreground')).move_to([0,.55,0])
self.play(FadeIn(label),FadeIn(q),run_time=.6)
self.wait({reveal-.6})
a=self.scene_text('动词：放弃、抛弃',font_size=38,color=self.style_color('emphasis')).move_to([0,-1.1,0])
self.play(FadeIn(a),run_time=.5)'''
 section['beats'][4]['visual']='显示正确英文例句与abandon a plan常用搭配，不遗漏旁白所讲搭配。'
 beat['visual']='问题先出现；实际提问旁白结束后停顿2秒，再显示动词：放弃、抛弃，留至少1.8秒读答案。'
 pipe.validate_snippets(snippets,len(section['beats']));rev=max(int(x.name.split('_')[-1]) for x in (out/'section_1').glob('revision_*'))+1
 write_json(archive/'code.json',snippets);write_json(archive/'storyboard.json',story)
 print('Rendering refined word story',rev,flush=True);video=pipe.render(section,snippets,rev)
 frames=sample_beat_frames(video,archive/f'review_{rev}',section['beats'],12)
 pipe.active_stage='review';review=pipe.vision.json(pipe.prompt('review',review_prompt(section,pipe.templates)),pipe.validate_feedback,images=frames);review['reviewed_revision']=rev
 write_json(archive/f'review_{rev}.json',review);print(json.dumps(review,ensure_ascii=False),flush=True)
 if review['has_issues']:raise RuntimeError('Refined story requires further review; previous film preserved')
 rendered['section_1']={'video':str(video),'revision':rev}
 write_json(out/'section_1_review_99.json',review);write_json(out/'section_1_code.json',snippets);write_json(out/'storyboard_assets.json',story);write_json(out/'reviewed.json',rendered)
 duration=write_subtitles(section['beats'],out/'subtitles.srt');mux(video,out/'narration.wav',out/'subtitles.srt',out/'final.mp4',duration)
 manifest.update(status='complete',media=probe(out/'final.mp4'),visual_review=review_summary(out,rendered,True),human_refinement='Show collocation and answer after genuine two-second recall pause; original narration retained')
 write_json(out/'manifest.json',manifest);write_json(out/'review_status.json',manifest['visual_review']);write_json(out/'timeline.json',section['beats'])
 write_json(project/'showcase_receipt.json',{'template':'word_story','result':str(out/'final.mp4'),'status':'generated','human_review':'pending after recall refinement'})
 print('Word story refined; inspect actual ending before publishing.',flush=True)
