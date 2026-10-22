"""Publish only proof-bound, visually reviewed, completely decoded real films."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from editing import inspect_media
from video_project import write_json
out=ROOT/'web/public/showcase';out.mkdir(exist_ok=True)
records=[]
for name,identity,title,description in [
 ('truth-teaching-v4','truth_logic','真假话实验室 · 先找矛盾','120秒原创练习。四个角色保留原话，先找互补命题，再取反缩小范围，逐行假设并回代。有限域验算、独立语义核对及18帧视觉审核通过，最终文件已完整解码。'),
 ('truth-exam-v1','truth_logic_exam','真假话实验室 · 兵团真题','2021兵团行政执法类行测网友回忆题。先识别甲丁同义，假设都真制造冲突，再用16种参与组合验证A；明确区分“甲参与”和“只有甲参与”。题干出处与选项已归档，视频120秒，审核与最终解码通过。')]:
 project=ROOT/'video_projects'/name;final=project/'output/final.mp4';accept=json.loads((project/'output/logic_final_acceptance.json').read_text())
 assert 'entire final film decoded' in accept['checks']
 assert hashlib.sha256(final.read_bytes()).hexdigest()==accept['final_sha256']
 manifest=json.loads((project/'output/manifest.json').read_text());assert manifest['status']=='complete' and manifest['visual_review']['passed'] is True
 info=inspect_media(final,max_seconds=180);assert info['width']==1920 and info['height']==1080
 shutil.copy2(final,out/(identity+'.mp4'))
 subprocess.run(['ffmpeg','-v','error','-y','-ss','4','-i',str(final),'-frames:v','1','-vf','scale=960:-2','-threads','1',str(out/(identity+'.jpg'))],check=True,timeout=45)
 write_json(out/(identity+'.json'),{**accept,'title':title,'project':name,'media':info})
 records.append({'id':identity,'title':title,'description':description,'credit':'实际制作与验收 · 2026-10-22','license':'原创图解；真题题干出处见来源说明','source':'/showcase/SOURCES.md','duration':round(info['duration']),'kind':'creation'})
file=ROOT/'templates/showcase.json';old=json.loads(file.read_text());ids={r['id'] for r in records};write_json(file,[r for r in old if r['id'] not in ids]+records)
print('Published',', '.join(ids))
