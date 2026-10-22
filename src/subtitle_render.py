"""Readable lower-screen subtitles rendered by FFmpeg's open-source libass."""
import re
import unicodedata
from pathlib import Path


def wrap_caption(text, width):
    # ASS override tags/backslashes from user input are always literal text.
    text=text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\r',' ').replace('\n',' ')
    lines=[];line='';used=0
    tokens=re.findall(r'[A-Za-z0-9]+(?:[.,:/%-][A-Za-z0-9]+)*|.',text)
    tokens=[piece for token in tokens for piece in (list(token) if len(token)>width else [token])]
    for token in tokens:
        size=sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in token)
        if used+size>width and line:lines.append(line.strip());line='';used=0
        line+=token;used+=size
    if line.strip():lines.append(line.strip())
    return lines


def ass_time(seconds):
    n=max(0,round(seconds*100));hours,n=divmod(n,360000);minutes,n=divmod(n,6000);whole,fraction=divmod(n,100)
    return f'{hours}:{minutes:02}:{whole:02}.{fraction:02}'


def write_ass(srt, destination, width, height):
    portrait=height>width;font=max(24,round(height*(.024 if portrait else .041)))
    margin=round(height*.06);horizontal=round(width*.08)
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Noto Sans CJK SC,{font},&H00FFFFFF,&H00FFFFFF,&H001A1511,&H80000000,0,0,0,0,100,100,0,0,1,2.5,0,2,{horizontal},{horizontal},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    blocks=re.split(r'\n\s*\n',Path(srt).read_text(encoding='utf8').strip());events=[]
    def seconds(value):
        h,m,s=map(float,value.replace(',','.').split(':'));return h*3600+m*60+s
    for block in blocks:
        rows=block.splitlines()
        if len(rows)<3 or '-->' not in rows[1]:raise ValueError('字幕时间格式错误')
        start,end=[seconds(x.strip()) for x in rows[1].split('-->')];text=' '.join(rows[2:]);lines=wrap_caption(text,30 if portrait else 64)
        # Long fallback cues are split in time, keeping at most two short lines.
        pages=[lines[i:i+2] for i in range(0,len(lines),2)]
        for i,page in enumerate(pages):
            a=start+(end-start)*i/len(pages);b=start+(end-start)*(i+1)/len(pages)
            caption='\\N'.join(page);events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Caption,,0,0,0,,{caption}')
    Path(destination).write_text(header+'\n'.join(events)+'\n',encoding='utf8')
    return destination


def filter_path(path):
    # FFmpeg filter quoting is separate from shell quoting; no shell is used.
    return str(Path(path).resolve()).replace('\\','\\\\').replace(':','\\:').replace("'","'\\''").replace('[','\\[').replace(']','\\]').replace(',','\\,')
