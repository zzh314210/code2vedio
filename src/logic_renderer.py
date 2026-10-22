"""Deterministic diagram/motion renderer using Pillow + FFmpeg.

Unlike generated Manim snippets this engine only consumes verified finite-model
proofs. It renders identities, contradiction links and enumerations from the same
state, with timed, reversible emphasis and no model-generated executable code.
"""
import json
import math
import subprocess
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from logic_contract import digest, describe, validate_plan_handoff

RENDERER_VERSION='pillow-ffmpeg-logic-v3'
RENDERER_SHA256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()
from media import ffmpeg_binary

W,H=1920,1080
BG='#F7F4ED'; INK='#202D45'; MUTED='#687384'; LINE='#DCDDD9'; BLUE='#346CED'; GREEN='#11816A'; RED='#D34B55'; GOLD='#BD7722'
COLORS=['#4778CE','#9664C2','#398A78','#CC7B45']
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'

@lru_cache(maxsize=90)
def font(size,bold=False):return ImageFont.truetype(BOLD if bold else FONT,size)


@lru_cache(maxsize=512)
def text_tile(value,size,fill,bold,anchor):
    f=font(size,bold);box=f.getbbox(value,anchor=anchor)
    tile=Image.new('RGBA',(max(1,box[2]-box[0]),max(1,box[3]-box[1])))
    ImageDraw.Draw(tile).text((-box[0],-box[1]),value,font=f,fill=fill,anchor=anchor)
    return tile,box


def text(d,xy,value,size=32,fill=INK,bold=False,anchor=None):
    tile,box=text_tile(str(value),size,fill,bold,anchor)
    d._image.paste(tile,(round(xy[0]+box[0]),round(xy[1]+box[1])),tile)


def wrap(value,width,size,max_lines=5):
    lines=[];line=''
    for char in value:
        if char=='\n' or font(size).getlength(line+char)>width:
            lines.append(line);line='' if char=='\n' else char
        else:line+=char
    if line:lines.append(line)
    if len(lines)>max_lines:raise ValueError('题干文字无法在安全区域清晰展示，请拆分题干')
    return lines


def paragraph(d,xy,value,width,size=32,fill=INK,bold=False,max_lines=5):
    lines=wrap(value,width,size,max_lines)
    for i,l in enumerate(lines):text(d,(xy[0],xy[1]+i*(size+11)),l,size,fill,bold)


def smooth(t):
    t=max(0,min(1,t));return t*t*(3-2*t)


def avatar(d,x,y,i,active=False,truth=None):
    c=COLORS[i]
    # Four distinct silhouettes, expressive brows, skin and lapels; no icons
    # pretending to be people. Labels fix identity throughout the lesson.
    d.ellipse((x-60,y+8,x+60,y+108),fill=c)
    d.polygon([(x-18,y+10),(x,y+46),(x+18,y+10)],fill='#FFFFFF')
    d.rounded_rectangle((x-16,y-8,x+16,y+30),8,fill='#E7B497')
    d.ellipse((x-43,y-73,x+43,y+13),fill='#F0C7AA',outline=INK,width=2)
    if i==0:
        d.pieslice((x-46,y-79,x+45,y-12),180,355,fill=INK)
        d.polygon([(x-39,y-47),(x-10,y-73),(x+30,y-48),(x+39,y-70),(x-35,y-75)],fill=INK)
    elif i==1:
        d.arc((x-45,y-79,x+45,y+16),170,360,fill=INK,width=12)
        for s in [-1,1]:d.ellipse((x+s*21-14,y-43,x+s*21+14,y-16),outline=INK,width=3)
        d.line((x-6,y-29,x+6,y-29),fill=INK,width=3)
    elif i==2:
        d.arc((x-44,y-79,x+44,y+15),160,365,fill='#493B36',width=15)
        d.ellipse((x+30,y-87,x+59,y-57),fill='#493B36')
    else:
        d.rounded_rectangle((x-45,y-78,x+45,y-48),10,fill=INK)
        d.polygon([(x-41,y-55),(x-20,y-31),(x-8,y-55)],fill=INK)
    if i!=1:
        for dx in [-17,17]:d.ellipse((x+dx-3,y-32,x+dx+3,y-26),fill=INK)
    d.arc((x-12,y-23,x+12,y-5),0,160,fill=INK,width=2)
    text(d,(x,y+120),'甲乙丙丁'[i],38,INK,True,'mt')
    if truth is not None:
        label='真话' if truth else '假话';color=GREEN if truth else RED
        d.rounded_rectangle((x+53,y+110,x+145,y+158),14,fill=color)
        text(d,(x+99,y+112),label,28,'#FFFFFF',True,'mt')


def base(proof,beat,index,t):
    image=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(image)
    # Restrained paper grid only in margins, no decorative texture behind text.
    for x in range(30,W,32):
        for y in (26,H-26):d.ellipse((x,y,x+2,y+2),fill='#E6E1D6')
    text(d,(80,48),'真假话实验室',28,BLUE,True)
    text(d,(1840,48),f'{index+1:02d} / 06',28,MUTED,False,'rt')
    text(d,(80,94),beat['title'],55,INK,True)
    steps=['读题','找关系','作假设','看组合','验结论','记方法'] if proof.get('version')==2 else ['读题','找矛盾','锁真假','作假设','验唯一','记方法']
    for i,s in enumerate(steps):
        x=1000+i*142
        d.rounded_rectangle((x,108,x+124,157),13,fill=BLUE if i==index else '#EAE9E3')
        text(d,(x+62,113),s,25,'#FFFFFF' if i==index else MUTED,i==index,'mt')
    c=proof['contract'];a,b=(proof['equivalent_pair'] if proof.get('version')==2 else proof['contradiction_pairs'][0]);truth=proof['answer']['truth']
    for i,s in enumerate(c['statements']):
        x=80+i*446;cx=x+212
        focus=(index==0 and i==min(3,int(t/2))) or (index==1 and i in (a,b)) or (index==2 and (i in (0,2,3) if proof.get('version')==2 else i not in (a,b))) or index==4
        border=(BLUE if index==1 else RED if index==2 else COLORS[i]) if focus else LINE
        d.rounded_rectangle((x,205,x+422,535),24,fill='#FFFFFF',outline=border,width=4 if focus else 2)
        value=truth[i] if index==4 else False if index==2 and c['true_count']==1 and i not in (a,b) else None
        avatar(d,cx,295,i,focus,value)
        # Quote remains at a fixed position: no identity or text drift.
        size=31
        while len(wrap(s['text'],374,size,max_lines=10))>2 and size>24:size-=1
        paragraph(d,(x+24,441),s['text'],374,size,INK,max_lines=2)
    d.rounded_rectangle((80,927,1840,1037),22,fill='#FFFFFF',outline=LINE,width=1)
    cue=next((s['text'] for s in beat.get('subtitles',[]) if s['start']<=t<s['end']), '')
    if cue:paragraph(d,(125,945),cue,1670,36,INK,max_lines=2)
    return image


def frame(proof,beat,index,t,duration):
    image=base(proof,beat,index,t);d=ImageDraw.Draw(image);c=proof['contract']
    if proof.get('version')==2:
        boolean_content(d,proof,beat,index,t,duration)
        progress_bar(d,index,t,duration)
        return image
    a,b=proof['contradiction_pairs'][0];who=c['variable']['label'];answer=proof['answer']
    if index==0:
        d.rounded_rectangle((80,550,1840,865),28,fill='#ECEFF8')
        text(d,(135,585),'题目条件',27,BLUE,True)
        text(d,(135,635),f'{who}只有一人  ·  恰好 {c["true_count"]} 人说真话',52,INK,True)
        text(d,(135,720),'先圈条件，再判断「话」，最后找「人」。',36,MUTED)
        text(d,(135,790),'绿色 ✓ 真话       红色 × 假话       蓝色 ↔ 矛盾关系',29,MUTED)
    elif index==1:
        xa=292+a*446;xb=292+b*446;y=554
        d.line((xa,540,xa,y,xb,y,xb,540),fill=BLUE,width=5)
        q=smooth(t/1.4);end=xa+(xb-xa)*q
        d.ellipse((end-9,y-9,end+9,y+9),fill=BLUE)
        text(d,(960,595),f'{c["people"][a]} ↔ {c["people"][b]}',50,BLUE,True,'mt')
        text(d,(960,677),'同一件事：一个肯定，一个否定',40,INK,True,'mt')
        text(d,(960,748),'必有一真一假  ≠  已经知道谁真谁假',36,MUTED,False,'mt')
        # Show both admissible cases together. An animated single case can
        # look like a determined verdict when paused or sampled for review.
        labels=[f'可能 1：{c["people"][a]}真 / {c["people"][b]}假',f'可能 2：{c["people"][a]}假 / {c["people"][b]}真']
        for n,label in enumerate(labels):
            x=130+n*850
            d.rounded_rectangle((x,799,x+795,866),14,fill='#FFFFFF',outline=BLUE,width=2)
            text(d,(x+28,809),label+' · 待定',30,BLUE,True)
    elif index==2:
        d.rounded_rectangle((80,550,1840,865),28,fill='#F0ECE5')
        text(d,(130,582),f'真话名额：{c["true_count"]} 句',42,INK,True)
        text(d,(690,588),f'矛盾对用去 1 句 → 剩余 {c["true_count"]-1} 句',34,BLUE,True)
        others=[i for i in range(4) if i not in (a,b)]
        for n,i in enumerate(others):
            y=658+n*82
            if c['true_count']==1:
                text(d,(130,y),f'{c["people"][i]}：'+c['statements'][i]['text'],32,RED)
                text(d,(805,y),'假 → 取反 →',31,BLUE,True)
                start=next((cue['start'] for cue in beat.get('subtitles',[]) if c['people'][i]+'的话取反' in cue['text']),6+n*4)
                if t>=start: text(d,(1100,y),describe(c['statements'][i]['claim'],who,True),34,INK,True)
            else:text(d,(130,y),f'{c["people"][i]}：'+c['statements'][i]['text'],32,INK)
        text(d,(130,815),'取反针对完整命题。先锁定范围，再把候选逐句回代。',28,MUTED)
    elif index==3:
        # All rows calculated from the proof, never from narration guesses.
        x0=100;y0=555;rowh=55;xs=[150,690,880,1070,1260,1480,1700]
        headers=[f'假设{who}是','甲','乙','丙','丁','真话数','检验']
        for x,h in zip(xs,headers):text(d,(x,y0),h,27,MUTED,True)
        row_cues=[(cue['start'],i) for i,r in enumerate(proof['rows']) for cue in beat.get('subtitles',[]) if '假设是'+r['actor'] in cue['text']]
        active=next((i for start,i in reversed(row_cues) if t>=start),0)
        if t>max((cue['end'] for cue in beat.get('subtitles',[]) if '假设是' in cue['text']),default=duration):
            active=next(i for i,r in enumerate(proof['rows']) if r['valid'])
        for i,r in enumerate(proof['rows']):
            y=y0+51+i*rowh
            if i==active:d.rounded_rectangle((80,y-4,1840,y+48),12,fill='#E5ECFD')
            text(d,(xs[0],y),r['actor'],30,INK,True)
            for x,v in zip(xs[1:5],r['truth']):text(d,(x,y),'✓' if v else '×',32,GREEN if v else RED,True)
            text(d,(xs[5],y),r['true_count'],30,INK,True)
            text(d,(xs[6],y),'保留' if r['valid'] else '排除',28,GREEN if r['valid'] else MUTED,r['valid'])
        y=y0+58+len(proof['rows'])*rowh
        text(d,(100,y),f'每行独立代回原话；恰好 {c["true_count"]} 句真话才成立。',28,MUTED)
    elif index==4:
        d.rounded_rectangle((80,550,1840,865),28,fill='#E6F1EC')
        text(d,(130,584),f'唯一解：{who}是 {answer["actor"]}',53,GREEN,True)
        text(d,(130,667),'四句原话依次为  '+ '   /   '.join('真' if v else '假' for v in answer['truth']),40,INK,True)
        speakers='、'.join(c['people'][i] for i,v in enumerate(answer['truth']) if v)
        text(d,(130,742),f'说真话的是 {speakers}   ·   真话数 {answer["true_count"]} = 题设 {c["true_count"]}',37,GREEN,True)
        text(d,(130,809),'结论来自逐行验算，所有其他候选均不满足条件。',29,MUTED)
    else:
        titles=['找矛盾','锁真假','假设回代'];notes=['同一命题与它的否定','用真话总数约束其余人','逐句检验，只留符合题设的行']
        for i,(title,note) in enumerate(zip(titles,notes)):
            x=80+i*598
            d.rounded_rectangle((x,550,x+564,785),24,fill='#FFFFFF',outline=BLUE if i==min(2,int(t/2.4)) else LINE,width=3)
            text(d,(x+32,577),f'0{i+1}',30,BLUE,True);text(d,(x+32,630),title,44,INK,True)
            paragraph(d,(x+32,711),note,502,27,MUTED,max_lines=2)
        text(d,(960,825),f'本题：{who}是{answer["actor"]}。做事的人与说真话的人，要分开判断。',34,INK,True,'mt')
    progress_bar(d,index,t,duration)
    return image


def render_logic(section,proof,destination,video,progress=None):
    if video.get('orientation','landscape')!='landscape':
        raise ValueError('真假话图解目前仅支持横屏，避免竖屏压缩导致原话和真值表不可读。请选择横屏。')
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    fps=int(video.get('fps',30));beats=section['beats']
    validate_plan_handoff({'proof_hash':proof['proof_hash'],'sections':[section]},proof,'storyboard')
    if [b.get('scene_id') for b in beats]!=['question','contradiction','deduction','enumerate','verify','recap']:raise ValueError('场景顺序或证据缺失')
    if any(b.get('proof_hash')!=proof['proof_hash'] for b in beats):raise ValueError('渲染所用证明与分镜不一致')
    cmd=[ffmpeg_binary(),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(destination)]
    receipts=[]
    with destination.with_suffix('.render.log').open('wb') as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        try:
            for index,beat in enumerate(beats):
                duration=beat['duration'];count=round(duration*fps)
                for n in range(count):
                    proc.stdin.write(frame(proof,beat,index,n/fps,duration).tobytes())
                receipts.append({'scene_id':beat['scene_id'],'proof_hash':proof['proof_hash'],'frames':count,'fps':fps,'duration':count/fps,'narration_sha256':digest(beat['narration'])})
                if progress:progress(index+1,len(beats))
            proc.stdin.close()
            if proc.wait(timeout=90):raise RuntimeError('图解编码失败，详见 .render.log')
        except BaseException:
            proc.kill();proc.wait();destination.unlink(missing_ok=True);raise
    destination.with_suffix('.receipt.json').write_text(json.dumps({'engine':RENDERER_VERSION,'renderer_sha256':RENDERER_SHA256,'proof_hash':proof['proof_hash'],'scenes':receipts},ensure_ascii=False,indent=2))
    return destination


def progress_bar(d,index,t,duration):
    d.rounded_rectangle((80,1058,1840,1065),3,fill=LINE)
    d.rounded_rectangle((80,1058,80+max(1,int(1760*(index+t/duration)/6)),1065),3,fill=BLUE)


def boolean_content(d,proof,beat,index,t,duration):
    def box(fill='#ECEFF8'):d.rounded_rectangle((80,550,1840,875),28,fill=fill)
    def line(y,value,size=38,color=INK):text(d,(130,y),value,size,color,True)
    if index==0:
        box();line(580,'2021 兵团行政执法类 · 网友回忆版',32,BLUE)
        line(638,'条件：两人说真话。问题：哪一人必定参与？',42)
        line(713,'A 甲是罪犯      B 乙是罪犯      C 丙是罪犯      D 丁是罪犯',31)
        line(798,'题目没有说「只有一人参与」；四个人分别判断。',30,MUTED)
    elif index==1:
        box();xa,xb=292,1630;y=565
        d.line((xa,540,xa,y,xb,y,xb,540),fill=BLUE,width=5)
        end=xa+(xb-xa)*smooth(t/1.8);d.ellipse((end-8,y-8,end+8,y+8),fill=BLUE)
        line(604,'丁的话 = 甲的话',48,BLUE)
        line(686,'都真  或  都假；不是「一真一假」',40)
        labels=['甲真  +  丁真','甲假  +  丁假']
        for n,label in enumerate(labels):
            x=130+n*850;active=int(t/3)%2==n
            d.rounded_rectangle((x,776,x+795,849),16,fill=GREEN if n==0 and active else RED if n==1 and active else '#FFFFFF')
            text(d,(x+28,787),label,36,'#FFFFFF' if active else MUTED,True)
    elif index==2:
        box('#F6ECE7');line(581,'假设：甲、丁都真',44,BLUE)
        start=next((q['start'] for q in beat.get('subtitles',[]) if '甲没参与' in q['text']),3)
        if t>=start:line(648,'甲没参与 + 乙参与  →  丙的话也真',39)
        reveal=next((q['start'] for q in beat.get('subtitles',[]) if '三句真话' in q['text']),8)
        if t>=reveal:
            line(725,'甲真 + 丙真 + 丁真  ≥ 3 句真话',44,RED)
            line(803,'题设只允许 2 句真话  →  冲突，排除假设',34,RED)
    elif index==3:
        line(548,'十六种参与组合 · 逐句回代，恰好两真才保留',32,BLUE)
        # A green row denotes a whole possible world, not a claim that all
        # listed people necessarily participated. All worlds remain visible.
        for i,r in enumerate(proof['rows']):
            col=i%4;row=i//4;x=80+col*446;y=605+row*57
            fill='#E0F0E8' if r['valid'] else '#EBEAE5'
            d.rounded_rectangle((x,y,x+422,y+48),10,fill=fill)
            label=r['participants'] if r['participants']=='无人' else '、'.join(r['participants'])
            text(d,(x+15,y+4),label,26,GREEN if r['valid'] else MUTED,r['valid'])
            text(d,(x+405,y+5),f'{r["true_count"]}真 '+('✓' if r['valid'] else '×'),25,GREEN if r['valid'] else MUTED,True,'rt')
        line(850,'绿色组合全部包含甲。未被选中的人，不等于一定无辜。',27,GREEN)
    elif index==4:
        box('#E6F1EC');line(578,'必然结论：甲参与  →  选 A',50,GREEN)
        line(660,'假设甲没参与 → 丙真则乙参与 → 甲的话变真',34)
        line(732,'与「甲假」冲突  →  甲必须参与',40,BLUE)
        line(811,'能推出甲参与；不能无依据补成「只有甲参与」。',31,MUTED)
    else:
        titles=['辨关系','假设排除','回代验结论'];notes=['相同：同真同假；矛盾：一真一假','让假设和真话总数发生冲突','只选必然结论，不补题目没给的条件']
        for i,(title,note) in enumerate(zip(titles,notes)):
            x=80+i*598;active=min(2,int(t/3))==i
            d.rounded_rectangle((x,550,x+564,795),24,fill='#FFFFFF',outline=BLUE if active else LINE,width=4 if active else 2)
            text(d,(x+32,578),f'0{i+1}',30,BLUE,True);text(d,(x+32,635),title,44,INK,True)
            paragraph(d,(x+32,712),note,500,27,MUTED,max_lines=2)
        line(830,'本题答案 A。甲、丁假；乙、丙真。',34,GREEN)


def receipt_matches(video,section,proof):
    try:
        r=json.loads(Path(video).with_suffix('.receipt.json').read_text())
        if r.get('engine')!=RENDERER_VERSION or r.get('renderer_sha256')!=RENDERER_SHA256 or r.get('proof_hash')!=proof['proof_hash']:return False
        return len(r['scenes'])==len(section['beats']) and all(a['scene_id']==b['scene_id'] and a['narration_sha256']==digest(b['narration']) and abs(a['duration']-b['duration'])<.04 for a,b in zip(r['scenes'],section['beats']))
    except (OSError,ValueError,KeyError,TypeError):return False
