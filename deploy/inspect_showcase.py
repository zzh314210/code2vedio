"""Create timed contact sheets for actual template-film inspection."""
import argparse,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('--section',default='section_1');p.add_argument('--revision',type=int,default=0);a=p.parse_args()
output=a.project/'output';timing=json.loads((output/'storyboard_assets.json').read_text());section=next(s for s in timing['sections'] if s['id']==a.section)
videos=list((output/a.section/f'revision_{a.revision}'/'media').rglob('lesson.mp4'))
if len(videos)!=1:raise SystemExit('No complete section video')
review=output/'contact-review';review.mkdir(exist_ok=True);frames=[];at=0
font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',17)
for i,beat in enumerate(section['beats']):
 print(i+1,round(at,2),round(at+beat['duration'],2),beat['narration'])
 for index,fraction in enumerate([.3,.85]):
  target=review/f'{a.section}-{a.revision}-{i}-{index}.jpg';timestamp=at+beat['duration']*fraction
  subprocess.run(['ffmpeg','-v','error','-y','-ss',str(timestamp),'-i',str(videos[0]),'-frames:v','1','-vf','scale=640:-2','-threads','1',str(target)],check=True)
  image=Image.open(target).convert('RGB');tile=Image.new('RGB',(640,image.height+30),'#eef1f4');tile.paste(image,(0,30));ImageDraw.Draw(tile).text((12,5),f'{i+1} · {timestamp:.1f}s · {beat["caption"]}',font=font,fill='#233746');frames.append(tile)
 at+=beat['duration']
canvas=Image.new('RGB',(1280,sum(x.height for x in frames[::2])),'white');y=0
for i in range(0,len(frames),2):
 canvas.paste(frames[i],(0,y));canvas.paste(frames[i+1],(640,y));y+=frames[i].height
result=review/f'{a.section}-{a.revision}.jpg';canvas.save(result,quality=90);print(result)
