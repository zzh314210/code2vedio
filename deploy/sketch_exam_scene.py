"""Original hand-drawn civil-service exam lesson; all drawings are procedural."""
import json
from pathlib import Path
import numpy as np
from manim import *
from handdrawn_runtime import sketch_shape

PAPER='#FBF7EE';INK='#263F4B';BLUE='#216F9C';GREEN='#427C5A';ORANGE='#BD673B';MUTED='#78877F';LINE='#DED9CC'
class ExamSketch(Scene):
    def style_color(self,name):return BLUE
    def text(self,value,size=28,color=INK):return Text(value,font='Noto Sans CJK SC',font_size=size,color=color)
    def rough(self,w,h,x=0,y=0,color=BLUE,fill=None,seed=37):return sketch_shape(self,'rectangle',width=w,height=h,center=(x,y,0),color=color,fill=fill,seed=seed)
    def line(self,start,end,color=BLUE):return sketch_shape(self,'line',points=[[*start,0],[*end,0]],color=color)
    def label(self,value,x,y,size=28,color=INK):return self.text(value,size,color).move_to([x,y,0])
    def card(self,x,y,w,h,title,detail,color=BLUE):
        return VGroup(self.rough(w,h,x,y,color),self.label(title,x,y+.28,32,color),self.label(detail,x,y-.36,21,MUTED))
    def cow(self,x,y,color=GREEN):
        head=sketch_shape(self,'ellipse',width=.42,height=.32,center=(x,y,0),color=color)
        horns=VGroup(self.line((x-.18,y+.08),(x-.28,y+.25),color),self.line((x+.18,y+.08),(x+.28,y+.25),color))
        eyes=VGroup(Dot([x-.085,y+.03,0],radius=.018,color=color),Dot([x+.085,y+.03,0],radius=.018,color=color))
        return VGroup(head,horns,eyes)
    def page(self,index,title,kicker):
        if getattr(self,'content',None):self.play(FadeOut(self.content,shift=UP*.08),run_time=.35)
        self.content=VGroup()
        header=self.label(title,0,2.55,38)
        subtitle=self.label(kicker,0,1.88,20,MUTED)
        number=self.label(f'{index:02d} / 06',5.8,3.38,16,MUTED)
        self.content.add(header,subtitle,number)
        self.play(FadeIn(header,shift=UP*.08),FadeIn(subtitle),FadeIn(number),run_time=.65)
        progress=Line([-6.4,-3.02,0],[-6.4+12.8*index/6,-3.02,0],color=GREEN,stroke_width=3)
        self.content.add(progress);self.add(progress)
    def show(self,*items,run_time=.8):
        self.content.add(*items);self.play(*[FadeIn(item,shift=UP*.08) for item in items],run_time=run_time)
    def finish(self,start,duration):self.wait(max(.1,duration-(self.renderer.time-start)))
    def construct(self):
        self.camera.background_color=PAPER
        timeline=json.loads((Path(__file__).parent/'timeline.json').read_text())
        dots=VGroup(*[Dot([x,y,0],radius=.009,color=LINE) for x in np.arange(-6.8,7,.45) for y in np.arange(-3.8,4,.45)])
        self.add(dots,self.label('行测  /  数量关系',-5.16,3.38,18,BLUE),self.label('FRAME  ·  手绘课堂',4.8,-3.65,13,MUTED))
        self.add(Line([-6.4,3.02,0],[6.4,3.02,0],color=LINE,stroke_width=1))
        start=self.renderer.time
        self.page(1,'草会长，时间怎么算？','原创例题  ·  每头牛每天吃草量相同，草均匀生长')
        cards=[self.card(-4.2,.45,3.65,1.7,'24 头牛','6 天吃完'),self.card(0,.45,3.65,1.7,'21 头牛','8 天吃完'),self.card(4.2,.45,3.65,1.7,'18 头牛','多少天吃完？',ORANGE)]
        for card in cards:self.show(card,run_time=.55)
        for x in [-4.2,0,4.2]:self.show(self.cow(x,1.48),run_time=.2)
        self.show(self.label('A. 10天       B. 12天       C. 14天       D. 16天',0,-1.35,27),self.label('先别套反比例：这片草地每天都在长草。',0,-2.23,23,ORANGE))
        self.finish(start,timeline[0]['duration'])
        start=self.renderer.time
        self.page(2,'多出的草，来自多出的 2 天','统一单位：1 份草 = 1 头牛 1 天的食量')
        self.show(self.label('6 天',-5.6,.8,23),self.label('8 天',-5.6,-.15,23))
        bar1=self.rough(7.2,.55,-.5,.8,BLUE,'#C6DCE5');bar2=self.rough(8.4,.55,.1,-.15,GREEN,'#D0DFC9')
        self.content.add(bar1,bar2);self.play(Create(bar1),run_time=1);self.play(Create(bar2),run_time=1)
        self.show(self.label('24 × 6 = 144 份',.1,.8,22),self.label('21 × 8 = 168 份',.1,-.15,22))
        delta=self.rough(1.2,.55,3.7,-.15,ORANGE,'#EDD6BE');self.show(delta)
        self.show(self.label('多长 2 天  →  多出 168 − 144 = 24 份',0,-1.15,27,ORANGE))
        self.show(self.label('每天新长：24 ÷ 2 = 12 份',0,-2.12,34,GREEN))
        self.finish(start,timeline[1]['duration'])
        start=self.renderer.time
        self.page(3,'先让 12 头牛，抵消每天新长的草','理解“净消耗”：剩下的牛，才在吃原来的草')
        herd=VGroup(*[self.cow(-5.3+col*.72, .9-row*.67,GREEN if col<4 else ORANGE) for row in range(3) for col in range(6)])
        self.content.add(herd);self.play(LaggedStart(*[FadeIn(c) for c in herd],lag_ratio=.06),run_time=1.5)
        self.show(self.label('12 头：吃掉新增',-4.2,-1.48,23,GREEN),self.label('6 头：消耗存量',-1.1,-1.48,23,ORANGE))
        self.show(self.rough(4.7,2.3,3.3,.15,ORANGE),self.label('18 − 12 = 6',3.3,.45,36,ORANGE),self.label('每天净消耗 6 份原有草',3.3,-.4,21))
        self.show(self.label('净消耗 = 牛的数量 − 每天新长的草',0,-2.25,28,BLUE))
        self.finish(start,timeline[2]['duration'])
        start=self.renderer.time
        self.page(4,'回到已知条件，算出最初有多少草','24 头牛吃 6 天；每天有 12 份新草补进来')
        blocks=VGroup(*[VGroup(self.rough(1.55,1.1,-4.6+i*1.85,.4,BLUE,'#D0E1E8',seed=20+i),self.label('12 份',-4.6+i*1.85,.4,23,BLUE)) for i in range(6)])
        self.content.add(blocks);self.play(LaggedStart(*[FadeIn(b) for b in blocks],lag_ratio=.15),run_time=1.6)
        self.show(self.label('每天净消耗 24 − 12 = 12 份，持续 6 天',0,-.75,25))
        self.show(self.label('原有草量 =（24 − 12）× 6 = 72 份',0,-1.75,33,BLUE))
        self.finish(start,timeline[3]['duration'])
        start=self.renderer.time
        self.page(5,'18 头牛，需要 12 天','原有草量 ÷ 每天净消耗 = 吃完所需天数')
        self.show(self.label('72 ÷（18 − 12）= 12 天',0,.95,43,ORANGE))
        outline=self.rough(10,.7,0,-.1,GREEN);bar=Rectangle(width=9.8,height=.46,stroke_width=0,fill_color='#93B08C',fill_opacity=.55).move_to([0,-.1,0])
        self.show(outline,bar)
        self.show(self.label('初始 72 份',-4,-.85,20,MUTED),self.label('第 12 天：原有草耗尽',3.8,-.85,20,MUTED))
        self.play(bar.animate.stretch_to_fit_width(.02).align_to(outline,LEFT).shift(RIGHT*.1),run_time=4,rate_func=linear)
        self.show(self.label('选 B · 12 天',0,-1.9,40,GREEN))
        ring=sketch_shape(self,'ellipse',width=4.2,height=1.05,center=(0,-1.9,0),color=GREEN);self.content.add(ring);self.play(Create(ring),run_time=.8)
        self.finish(start,timeline[4]['duration'])
        start=self.renderer.time
        self.page(6,'记住顺序，不必死背公式','牛吃草、漏水池、排队消耗：本质都是“存量 + 增量”')
        steps=[self.card(-4.2,.5,3.65,1.9,'01 先求增长','两组总量差 ÷ 时间差',GREEN),self.card(0,.5,3.65,1.9,'02 再求存量','净消耗 × 已知天数',BLUE),self.card(4.2,.5,3.65,1.9,'03 最后算时间','原有存量 ÷ 净消耗',ORANGE)]
        for card in steps:self.show(card,run_time=.55)
        self.show(self.label('验证：21 − 12 = 9，72 ÷ 9 = 8 天  ✓',0,-1.18,26,GREEN))
        self.show(self.label('易错点：直接用“牛数 × 天数”当原有草量。',0,-2.1,24,ORANGE))
        self.finish(start,timeline[5]['duration'])
