"""Trusted layout primitives: editorial motion with explicit safe regions.

Kept in every selected template's project snapshot; model calls supply data only.
"""
import json,math
from pathlib import Path
import numpy as np
from manim import *

def palette(scene):
 return scene.lesson_style.get('style_palette') or {'foreground':'#233e45','primary':'#0b8484','emphasis':'#bd5737'}

def media_shot(scene,key,label='',motion='push',framing='contain'):
 if motion not in ['push','reveal','hold']:raise ValueError('Unknown media motion')
 if framing not in ['contain','cover']:raise ValueError('Unknown media framing')
 if len(label)>28:raise ValueError('Media label must be concise')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 max_w=config.frame_width*(.86 if framing=='cover' else .79);max_h=config.frame_height*(.48 if portrait else .52)
 image=scene.asset(key)
 if framing=='cover':
  if not hasattr(image,'pixel_array'):raise ValueError('Cover framing requires a raster photograph')
  pixels=image.pixel_array;h,w=pixels.shape[:2];ratio=max_w/max_h
  if w/h>ratio:
   crop=max(1,round(h*ratio));left=(w-crop)//2;pixels=pixels[:,left:left+crop]
  else:
   crop=max(1,round(w/ratio));top=(h-crop)//2;pixels=pixels[top:top+crop,:]
  image=ImageMobject(pixels.copy())
 image.scale(min(max_w/image.width,max_h/image.height)).move_to(UP*.12)
 border=RoundedRectangle(width=image.width+.12,height=image.height+.12,corner_radius=.12,stroke_color=p.get('primary','#0b8484'),stroke_width=1.2,fill_opacity=0).move_to(image)
 if label:
  text=scene.scene_text(label,font_size=30,color=p.get('foreground','#233e45'))
  if text.width>max_w:text.scale_to_fit_width(max_w)
  text.next_to(border,DOWN,buff=.22)
  # Captions occupy the lower .73 +/- .5 scene units. Reserve the entire
  # source label and the 2.5% camera push above that zone in both layouts.
  floor=-config.frame_height/2+1.43
  if text.get_bottom()[1]<floor:text.shift(UP*(floor-text.get_bottom()[1]))
  scene.play(FadeIn(text,shift=UP*.08),run_time=.4)
 scene.play(FadeIn(image,shift=UP*.15),Create(border),run_time=.8)
 if motion=='push':scene.play(image.animate.scale(1.025),border.animate.scale(1.025),run_time=2.8,rate_func=smooth)
 elif motion=='reveal':scene.play(Indicate(border,color=p.get('emphasis','#bd5737'),scale_factor=1.025),run_time=1)
 scene.wait(.5)
 return image

def knowledge_map(scene,items,active=0):
 if not isinstance(items,list) or not 2<=len(items)<=5 or any(not isinstance(s,str) or len(s)>12 for s in items):raise ValueError('Knowledge map requires 2–5 short labels')
 if not isinstance(active,int) or not 0<=active<len(items):raise ValueError('Invalid knowledge focus')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 w=min(2.2,config.frame_width*.34);h=.75
 positions=[np.array([(-1 if i%2==0 else 1)*w*.75,1.4-(i//2)*1.5,0]) for i in range(len(items))] if portrait else [np.array([(i-(len(items)-1)/2)*min(2.55,(config.frame_width-2.5)/len(items)),.5+(i%2)*.55,0]) for i in range(len(items))]
 nodes=[]
 for i,(title,pos) in enumerate(zip(items,positions)):
  color=p.get('emphasis','#bd5737') if i==active else p.get('primary','#0b8484')
  box=RoundedRectangle(width=w,height=h,corner_radius=.12,stroke_color=color,stroke_width=2,fill_color=color,fill_opacity=.1 if i==active else .035).move_to(pos)
  label=scene.scene_text(title,font_size=26,color=p.get('foreground','#233e45')).move_to(pos)
  if label.width>w-.2:label.scale_to_fit_width(w-.2)
  nodes.append(VGroup(box,label))
 for i in range(len(nodes)-1):scene.play(Create(Line(nodes[i].get_center(),nodes[i+1].get_center(),color=p.get('primary','#0b8484'),stroke_opacity=.25,stroke_width=2)),run_time=.15)
 scene.play(LaggedStart(*[FadeIn(n,shift=UP*.12) for n in nodes],lag_ratio=.12),run_time=1)
 scene.play(Circumscribe(nodes[active],color=p.get('emphasis','#bd5737'),buff=.12),run_time=1.1)
 scene.wait(.6)
 return VGroup(*nodes)

def _clip(points,xmin,xmax,ymin,ymax):
 # Sutherland–Hodgman clipping keeps geography inside the map viewport.
 for axis,bound,greater in [(0,xmin,True),(0,xmax,False),(1,ymin,True),(1,ymax,False)]:
  if not points:break
  output=[];previous=points[-1]
  for current in points:
   inside=lambda p:p[axis]>=bound if greater else p[axis]<=bound
   if inside(current)!=inside(previous):
    ratio=(bound-previous[axis])/(current[axis]-previous[axis]);output.append([previous[k]+ratio*(current[k]-previous[k]) for k in [0,1]])
   if inside(current):output.append(current)
   previous=current
  points=output
 return points

def map_story(scene,locations,active=0,connect=True,date='',event=''):
 if not isinstance(locations,list) or not 1<=len(locations)<=6:raise ValueError('Map needs 1–6 locations')
 for loc in locations:
  if not isinstance(loc,dict) or len(str(loc.get('name','')))>12 or not -85<=float(loc['lat'])<=85 or not -180<=float(loc['lon'])<=180:raise ValueError('Invalid map location')
 if not 0<=active<len(locations):raise ValueError('Invalid map focus')
 if len(date)>14 or len(event)>26:raise ValueError('Map event/date labels must stay concise')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 lons=[float(x['lon']) for x in locations];lats=[float(x['lat']) for x in locations]
 dx=max(12,max(lons)-min(lons));dy=max(10,max(lats)-min(lats));xmin=min(lons)-dx*.25;xmax=max(lons)+dx*.25;ymin=min(lats)-dy*.55;ymax=max(lats)+dy*.55
 w=config.frame_width*(.85 if portrait else .59);h=config.frame_height*(.32 if portrait else .39);center=np.array([0 if portrait else -1.4,1.25 if portrait else .6,0])
 # Fill the map viewport with surrounding geographic context instead of a
 # narrow horizontal strip when locations share similar latitudes.
 if not portrait:
  span_x=xmax-xmin;span_y=max(ymax-ymin,span_x*h/w)
  center_lat=(ymin+ymax)/2;ymin=max(-85,center_lat-span_y/2);ymax=min(85,center_lat+span_y/2)
 # Same uniform map projection for land, points, and connecting lines.
 scale=min(w/(xmax-xmin),h/(ymax-ymin));mid=np.array([(xmin+xmax)/2,(ymin+ymax)/2])
 def point(lon,lat):return np.array([(lon-mid[0])*scale,(lat-mid[1])*scale,0])+center
 area=RoundedRectangle(width=w+.2,height=h+.2,corner_radius=.1,stroke_color=p.get('primary','#0b8484'),stroke_opacity=.2,fill_color=p.get('primary','#0b8484'),fill_opacity=.035).move_to(center)
 land=VGroup();data=json.loads((Path(__file__).parent/'world_land.json').read_text())
 for geometry in data:
  for ring in geometry:
   points=_clip(ring,xmin,xmax,ymin,ymax)
   if len(points)>=3:
    poly=Polygon(*[point(*xy) for xy in points],stroke_width=.35,stroke_color=p.get('primary','#0b8484'),fill_color=p.get('primary','#0b8484'),fill_opacity=.13);land.add(poly)
 scene.add(area,land)
 dots=[]
 for i,loc in enumerate(locations):
  dot=Dot(point(loc['lon'],loc['lat']),radius=.075,color=p.get('emphasis','#bd5737') if i==active else p.get('primary','#0b8484'));dots.append(dot)
  scene.add(dot)
  label=scene.scene_text(str(i+1),font_size=19,color=p.get('emphasis','#bd5737')).next_to(dot,UP if float(loc['lat'])>=float(np.median(lats)) else DOWN,buff=.1);scene.add(label)
  text=scene.scene_text(f"{i+1}  {loc['name']}",font_size=27,color=p.get('emphasis','#bd5737') if i==active else p.get('primary','#0b8484'))
  pos=np.array([0,-1.55-i*.38,0]) if portrait else np.array([config.frame_width*.34,1.6-i*.55,0]);text.move_to(pos);scene.add(text)
 # Nearby cities stay at their true coordinates; a regional inset makes
 # their separation legible instead of moving locations to suit the layout.
 cluster=[i for i,a in enumerate(locations) if any(i!=j and math.hypot(a['lon']-b['lon'],a['lat']-b['lat'])<20 for j,b in enumerate(locations))]
 if not portrait and 2<=len(cluster)<=3 and len(locations)<=3:
  subset=[locations[i] for i in cluster];cx=config.frame_width*.34;cy=-1.05;iw=2.8;ih=2.0
  lo=min(x['lon'] for x in subset)-4;hi=max(x['lon'] for x in subset)+4;bot=min(x['lat'] for x in subset)-4;top=max(x['lat'] for x in subset)+4
  factor=min(iw/(hi-lo),ih/(top-bot))
  def inset_point(lon,lat):return np.array([(lon-(lo+hi)/2)*factor+cx,(lat-(bot+top)/2)*factor+cy,0])
  scene.add(RoundedRectangle(width=iw+.12,height=ih+.12,corner_radius=.08,stroke_color=p.get('primary','#0b8484'),stroke_width=1,stroke_opacity=.35).move_to([cx,cy,0]))
  for geometry in data:
   for ring in geometry:
    vertices=_clip(ring,lo,hi,bot,top)
    if len(vertices)>=3:scene.add(Polygon(*[inset_point(*xy) for xy in vertices],stroke_width=.3,stroke_color=p.get('primary','#0b8484'),fill_color=p.get('primary','#0b8484'),fill_opacity=.13))
  for i in cluster:
   loc=locations[i];dot=Dot(inset_point(loc['lon'],loc['lat']),radius=.06,color=p.get('emphasis','#bd5737') if i==active else p.get('primary','#0b8484'));scene.add(dot)
   label=scene.scene_text(str(i+1),font_size=20,color=dot.get_color()).next_to(dot,RIGHT,buff=.1);scene.add(label)
  scene.add(scene.scene_text('邻近地点放大',font_size=17,color=p.get('foreground','#233e45')).move_to([cx,.15,0]))
 if connect:
  for i in range(min(active,len(dots)-1)):
   if np.linalg.norm(dots[i+1].get_center()-dots[i].get_center())>.15:scene.play(Create(Line(dots[i].get_center(),dots[i+1].get_center(),color=p.get('emphasis','#bd5737'),stroke_width=2)),run_time=.5)
 scene.play(Flash(dots[active],color=p.get('emphasis','#bd5737'),flash_radius=.25),run_time=.8)
 note=scene.scene_text('地图定位示意 · 连线表示叙事关联',font_size=19,color=p.get('foreground','#233e45')).set_opacity(.65)
 note.move_to(np.array([0,-4.7 if portrait else -2.35,0]));scene.add(note)
 if date or event:
  caption=scene.scene_paragraph(' · '.join(x for x in [date,event] if x),width=config.frame_width*(.85 if portrait else .58),font_size=25,color=p.get('foreground','#233e45'))
  if caption.width>config.frame_width*.86:caption.scale_to_fit_width(config.frame_width*.86)
  caption.move_to([0 if portrait else -1.4,-4.05 if portrait else -1.8,0]);scene.play(FadeIn(caption,shift=UP*.08),run_time=.4)
 scene.wait(.8)
 return VGroup(area,land,*dots)


def _story_icon(name,height):
 if name not in {'banana','boat','bread','island','robot','cat','book'}:raise ValueError('Choose a built-in story character or prop')
 return SVGMobject(str(Path(__file__).parent/'noto'/(name+'.svg'))).set_height(height)


def story_scene(scene,actor='banana',prop='boat',place='bread',action='sail',setting='water'):
 """Recognizable licensed actors, fixed staging, and continuous physical actions."""
 if action not in {'sail','leave','arrive','discover'} or setting not in {'water','ground'}:raise ValueError('Unknown story action')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 left=-2.2 if portrait else -3.2;right=2.2 if portrait else 3.2
 level=-.8
 for row in range(2 if setting=='water' else 1):
  pts=[np.array([x,level-row*.28+(.07*math.sin(x*4) if setting=='water' else 0),0]) for x in np.linspace(-config.frame_width*.4,config.frame_width*.4,90)]
  line=VMobject().set_points_smoothly(pts).set_stroke(p.get('primary','#0b8484'),width=2,opacity=.5);scene.add(line)
 character=_story_icon(actor,1.5 if not portrait else 1.3)
 vessel=_story_icon(prop,1.2).move_to([left,level+.3,0])
 island=_story_icon(place,1.7).move_to([right,level+.45,0])
 character.move_to([left,level+1.3,0]);scene.add(vessel,character)
 if action=='sail':
  scene.play(vessel.animate.shift(RIGHT*.35),character.animate.shift(RIGHT*.35),run_time=1.5)
  drops=VGroup(*[Dot([left+.15+i*.17,level+.55,0],radius=.05,color=p.get('primary','#0b8484')) for i in range(3)])
  scene.play(LaggedStart(*[FadeIn(d,shift=DOWN*.25) for d in drops],lag_ratio=.3),run_time=.8)
  scene.play(Wiggle(character,scale_value=1.04,rotation_angle=.08),run_time=.8)
 elif action=='leave':
  scene.play(FadeIn(island,shift=UP*.1),run_time=.6)
  path=ArcBetweenPoints(character.get_center(),[right-.6,level+1.5,0],angle=-PI/3)
  scene.play(MoveAlongPath(character,path),vessel.animate.shift(DOWN*.6).set_opacity(.15),run_time=2.2)
  scene.play(FadeOut(vessel),run_time=.4)
 elif action=='arrive':
  scene.remove(vessel);character.move_to([left,level+.1,0]);scene.add(island)
  scene.play(character.animate.move_to([right,level+1.45,0]),run_time=2.2,rate_func=smooth)
  scene.play(Wiggle(character,scale_value=1.04,rotation_angle=.08),run_time=.7)
 else:
  scene.remove(vessel);scene.add(island);scene.play(character.animate.move_to([right-1,level+1.25,0]),run_time=1.5)
  scene.play(Indicate(island,scale_factor=1.08),run_time=.8)
 note=scene.scene_text('原创记忆联想 · 不是词源',font_size=19,color=p.get('foreground','#233e45')).set_opacity(.65).move_to([0,-2.25 if not portrait else -3.3,0]);scene.add(note)
 scene.wait(.6)


def vocabulary_card(scene,word,meaning,example='',quiz=False):
 if not word or len(word)>35 or not meaning or len(meaning)>24 or len(example)>100:raise ValueError('Use a short word, meaning, and example')
 p=palette(scene);width=config.frame_width*.82
 title=scene.scene_text(word,font_size=58,color=p.get('primary','#0b8484')).move_to([0,1.3,0])
 if title.width>width:title.scale_to_fit_width(width)
 definition=scene.scene_text(meaning,font_size=32,color=p.get('foreground','#233e45')).move_to([0,.2,0])
 if definition.width>width:definition.scale_to_fit_width(width)
 scene.play(FadeIn(title,shift=UP*.1),run_time=.6)
 if quiz:
  question=scene.scene_text('还记得它的意思吗？',font_size=30,color=p.get('foreground','#233e45')).move_to([0,.2,0]);scene.add(question)
  beat=scene.lesson_beats[scene._beat_index]
  answer=[cue['start'] for cue in beat.get('subtitles',[]) if any(term in cue['text'] for term in ['答案','是放弃','是抛弃','答对'])]
  reveal=max(2,answer[0] if answer else beat['duration']*.65)
  scene.wait(max(0,reveal-(scene.renderer.time-scene._beat_start)));scene.remove(question)
 scene.play(FadeIn(definition,shift=UP*.1),run_time=.5)
 if example:
  sentence=scene.scene_paragraph(example,width=width,font_size=30,color=p.get('foreground','#233e45')).move_to([0,-1.1,0]);scene.play(FadeIn(sentence),run_time=.6)
 scene.wait(.5)


def review_cards(scene,items):
 """A concise end-of-lesson summary; facts stay separate and readable."""
 if not isinstance(items,list) or not 2<=len(items)<=4:raise ValueError('Summary needs 2–4 facts')
 if any(not isinstance(x,dict) or not isinstance(x.get('title'),str) or len(x['title'])>10 or not isinstance(x.get('text'),str) or len(x['text'])>38 for x in items):raise ValueError('Keep each summary heading <=10 chars and fact <=38 chars')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 width=config.frame_width*(.82 if portrait else .37);height=1.65 if portrait else 1.8
 cards=[]
 for i,item in enumerate(items):
  pos=[0,3.1-i*2,0] if portrait else [(-1 if i%2==0 else 1)*3,1.15-(i//2)*2.15,0]
  box=RoundedRectangle(width=width,height=height,corner_radius=.12,stroke_color=p['primary'],stroke_opacity=.3,stroke_width=1.2,fill_color=p['primary'],fill_opacity=.04).move_to(pos)
  heading=scene.scene_text(item['title'],font_size=27,color=p['primary']).move_to(np.array(pos)+UP*.51)
  body=scene.scene_paragraph(item['text'],width=width-.5,font_size=27,color=p['foreground']).move_to(np.array(pos)+DOWN*.21)
  if body.height>height-.65:body.scale_to_fit_height(height-.65)
  cards.append(VGroup(box,heading,body))
 scene.play(LaggedStart(*[FadeIn(card,shift=UP*.12) for card in cards],lag_ratio=.3),run_time=2)
 scene.wait(.7)


def recall_card(scene,question,answer='',reveal=False):
 """Use separate question/answer beats to allow an actual spoken recall pause."""
 if not isinstance(question,str) or not 1<=len(question)<=55 or not isinstance(answer,str) or len(answer)>55:raise ValueError('Use a short recall question and answer')
 p=palette(scene);width=config.frame_width*.8
 label=scene.scene_text('回忆一下' if not reveal else '对照答案',font_size=25,color=p['primary']).move_to([0,1.8,0])
 prompt=scene.scene_paragraph(question,width=width,font_size=34,color=p['foreground']).move_to([0,.65,0])
 scene.play(FadeIn(label),FadeIn(prompt,shift=UP*.12),run_time=.6)
 if reveal:
  solution=scene.scene_paragraph(answer,width=width,font_size=34,color=p.get('emphasis',p['primary'])).move_to([0,-1.05,0]);scene.play(FadeIn(solution,shift=UP*.1),run_time=.6)
 else:
  hint=scene.scene_text('先试着自己回答，再看下一幕',font_size=24,color=p['primary']).move_to([0,-1.2,0]);scene.play(FadeIn(hint),run_time=.5)
 scene.wait(.5)


def function_plot(scene,coefficients=None,focus=1,offsets=None,mode='secant',x_range=None,y_range=None,label=''):
 """A polynomial, moving secant and exact tangent with clipped geometry.

 Coefficients are in ascending power order. Content comes from the task;
 arithmetic, graph coordinates and the layout stay deterministic.
 """
 coefficients=[0,0,1] if coefficients is None else coefficients
 offsets=[1,.5,.1] if offsets is None else offsets
 x_range=[-.5,2.5] if x_range is None else x_range
 y_range=[-.5,5] if y_range is None else y_range
 def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
 if not isinstance(coefficients,list) or not 1<=len(coefficients)<=6 or not all(finite(v) and abs(v)<=1000 for v in coefficients):raise ValueError('Use 1–6 finite polynomial coefficients in ascending power order')
 if mode not in {'secant','tangent'} or not isinstance(offsets,list) or not 1<=len(offsets)<=5 or not all(finite(h) and abs(h)>=.0001 for h in offsets):raise ValueError('Use 1–5 nonzero finite secant offsets')
 if any(not isinstance(r,list) or len(r)!=2 or not all(finite(v) for v in r) or not .01<=r[1]-r[0]<=10000 for r in [x_range,y_range]):raise ValueError('Graph ranges require two finite increasing bounds')
 if not finite(focus) or not x_range[0]<=focus<=x_range[1] or not isinstance(label,str) or len(label)>24:raise ValueError('Invalid graph focus or label')
 f=lambda x:sum(a*x**i for i,a in enumerate(coefficients))
 derivative=sum(i*a*focus**(i-1) for i,a in enumerate(coefficients) if i)
 y0=f(focus)
 if not y_range[0]<=y0<=y_range[1] or any(not x_range[0]<=focus+h<=x_range[1] or not y_range[0]<=f(focus+h)<=y_range[1] for h in offsets):raise ValueError('Focus and all moving points must be inside both graph ranges')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 foreground=p.get('foreground','#263e46');primary=p.get('primary','#327e85');accent=p.get('emphasis','#b86a35');muted=p.get('muted',foreground)
 center=[0,1.35,0] if portrait else [-2.7,.0,0]
 axes=Axes(x_range=[*x_range,(x_range[1]-x_range[0])/4],y_range=[*y_range,(y_range[1]-y_range[0])/4],x_length=6.1,y_length=3.7,axis_config={'color':muted,'stroke_width':1.5,'include_ticks':False,'include_tip':False}).move_to(center)
 # Never let an unbounded plot escape its coordinate rectangle.
 segments=[];points=[]
 for x in np.linspace(*x_range,321):
  y=f(x)
  if y_range[0]<=y<=y_range[1]:points.append(axes.c2p(x,y))
  elif points:
   if len(points)>1:segments.append(VMobject().set_points_as_corners(points).set_stroke(primary,width=3))
   points=[]
 if len(points)>1:segments.append(VMobject().set_points_as_corners(points).set_stroke(primary,width=3))
 if not segments:raise ValueError('Polynomial does not intersect the graph range')
 scene.add(axes,*segments)
 for axis,bounds in [('x',x_range),('y',y_range)]:
  rough=(bounds[1]-bounds[0])/5;power=10**math.floor(math.log10(rough))
  step=min([1,2,5,10],key=lambda n:abs(n-rough/power))*power
  for value in np.arange(math.ceil(bounds[0]/step)*step,bounds[1]+step*.001,step):
   value=round(float(value),8)
   if abs(value)<.001:continue
   pos=axes.c2p(value,0) if axis=='x' else axes.c2p(0,value)
   # Labels may sit outside the axes but inside the reserved graph panel.
   text=scene.scene_text(f'{value:g}',font_size=16,color=muted).move_to(pos+(DOWN*.2 if axis=='x' else LEFT*.25))
   if text.get_left()[0]>=-config.frame_width/2+.3:
    tick=Line(pos+(UP if axis=='x' else RIGHT)*.04,pos-(UP if axis=='x' else RIGHT)*.04,color=muted,stroke_width=1)
    scene.add(tick,text)
 scene.add(scene.scene_text('x',font_size=22,color=foreground).next_to(axes.x_axis.get_end(),RIGHT,buff=.12),scene.scene_text('y',font_size=22,color=foreground).next_to(axes.y_axis.get_end(),UP,buff=.12))
 # A line is clipped against the same data rectangle, not merely the frame.
 def endpoints(slope):
  pts=[]
  for x in x_range:
   y=y0+slope*(x-focus)
   if y_range[0]-1e-8<=y<=y_range[1]+1e-8:pts.append((x,y))
  if abs(slope)>1e-10:
   for y in y_range:
    x=focus+(y-y0)/slope
    if x_range[0]-1e-8<=x<=x_range[1]+1e-8:pts.append((x,y))
  pts=sorted(set(pts))
  if len(pts)<2:raise ValueError('No visible secant segment')
  return axes.c2p(*pts[0]),axes.c2p(*pts[-1])
 slope=lambda h:(f(focus+h)-y0)/h
 anchor=Dot(axes.c2p(focus,y0),radius=.065,color=accent)
 moving=Dot(axes.c2p(focus+offsets[0],f(focus+offsets[0])),radius=.065,color=primary)
 line=Line(*endpoints(slope(offsets[0])),color=accent,stroke_width=3)
 scene.play(FadeIn(anchor),FadeIn(moving),Create(line),run_time=.6)
 scene.add(scene.scene_text('A',font_size=22,color=accent).next_to(anchor,DOWN+RIGHT,buff=.1))
 moving_label=scene.scene_text('B',font_size=22,color=primary).next_to(moving,UP+RIGHT,buff=.12)
 moving_label.add_updater(lambda mob:mob.next_to(moving,UP+RIGHT,buff=.12));scene.add(moving_label)
 panel=np.array([0,-1.7,0]) if portrait else np.array([3.6,1.3,0]);panel_width=6.5 if portrait else 4.1
 title=scene.scene_text(label or ('割线趋向切线' if mode=='tangent' else '两点之间，看平均变化'),font_size=29,color=foreground).move_to(panel)
 if title.width>panel_width:title.scale_to_fit_width(panel_width)
 scene.play(FadeIn(title),run_time=.4)
 def readout(h):
  group=VGroup(scene.scene_text(f'h = {h:g}',font_size=33,color=primary),scene.scene_text(f'割线斜率 = {slope(h):g}',font_size=27,color=foreground)).arrange(DOWN,buff=.35).move_to(panel+DOWN*1.25)
  if group.width>panel_width:group.scale_to_fit_width(panel_width)
  return group
 info=readout(offsets[0]);scene.add(info);scene.wait(.5)
 previous=offsets[0]
 for h in offsets[1:]:
  origin=previous
  def move_point(mob,alpha):
   value=origin+(h-origin)*alpha;mob.move_to(axes.c2p(focus+value,f(focus+value)))
  def move_line(mob,alpha):
   value=origin+(h-origin)*alpha
   if abs(value)<1e-7:s=derivative
   else:s=slope(value)
   mob.put_start_and_end_on(*endpoints(s))
  scene.remove(info)
  scene.play(UpdateFromAlphaFunc(moving,move_point),UpdateFromAlphaFunc(line,move_line),run_time=1.15)
  info=readout(h);scene.add(info);scene.wait(.4);previous=h
 if mode=='tangent':
  tangent=Line(*endpoints(derivative),color=primary,stroke_width=3)
  final=VGroup(scene.scene_text('h → 0',font_size=33,color=primary),scene.scene_text(f'切线斜率 = {derivative:g}',font_size=29,color=accent)).arrange(DOWN,buff=.35).move_to(panel+DOWN*1.25)
  if final.width>panel_width:final.scale_to_fit_width(panel_width)
  moving_label.clear_updaters()
  scene.play(Transform(line,tangent),FadeOut(moving),FadeOut(moving_label),FadeOut(info),FadeIn(final),run_time=.8)
  hint=scene.scene_paragraph('趋近 0，不能直接除以 0',width=panel_width,font_size=22,color=muted).move_to(panel+DOWN*2.5);scene.add(hint)
 scene.wait(.5)
 return {'secant_slopes':[slope(h) for h in offsets],'tangent_slope':derivative,'curve_segments':segments,'axes':axes}


def formula_steps(scene,lines,title='',note=''):
 """One derivation, separate from a graph: fixed safe width and row count."""
 if not isinstance(lines,list) or not 1<=len(lines)<=4 or any(not isinstance(v,str) or not v.strip() or len(v)>65 for v in lines):raise ValueError('Use 1–4 concise formula steps')
 if not isinstance(title,str) or len(title)>30 or not isinstance(note,str) or len(note)>45:raise ValueError('Use short formula labels')
 p=palette(scene);portrait=config.frame_height>config.frame_width;w=config.frame_width*.82
 top=3.5 if portrait else 1.8;spacing=1.1 if portrait else .94
 if title:
  heading=scene.scene_paragraph(title,width=w,font_size=29,color=p['primary']).move_to([0,top+.55,0]);scene.add(heading)
 rendered=[]
 for i,value in enumerate(lines):
  text=scene.scene_text(value,font_size=36 if not portrait else 33,color=p.get('emphasis',p['primary']) if i==len(lines)-1 else p['foreground'])
  if text.width>w:text.scale_to_fit_width(w)
  text.move_to([0,top-.35-i*spacing,0]);rendered.append(text)
  scene.play(FadeIn(text,shift=UP*.12),run_time=.55);scene.wait(.45)
 scene.play(Circumscribe(rendered[-1],color=p['primary'],buff=.17),run_time=.7)
 if note:
  foot=scene.scene_paragraph(note,width=w,font_size=24,color=p['primary']).move_to([0,-2.3 if not portrait else -2.0,0]);scene.play(FadeIn(foot),run_time=.4)
 scene.wait(.5)
 return rendered


def _phase_disc(angle,radius,center,lit='#EFCB74',dark='#293A52'):
 """Orthographic visible lit area; 0=new, pi/2=first, pi=full.

 The terminator x = cos(angle)*sqrt(r²-y²) is the projection of a
 hemisphere. The right side waxes and the left wanes in the convention
 explicitly labelled on screen (north-up, northern hemisphere).
 """
 angle=float(angle)%(2*PI);center=np.asarray(center,dtype=float)
 disk=Circle(radius=radius,stroke_width=1.2,stroke_color=lit,fill_color=dark,fill_opacity=1).move_to(center)
 ys=np.linspace(-radius,radius,65);extent=np.sqrt(np.maximum(0,radius**2-ys**2));c=math.cos(angle)
 if angle<=PI:left=c*extent;right=extent
 else:left=-extent;right=-c*extent
 vertices=[center+np.array([x,y,0]) for x,y in zip(left,ys)]+[center+np.array([x,y,0]) for x,y in zip(right[::-1],ys[::-1])]
 glow=Polygon(*vertices,stroke_width=0,fill_color=lit,fill_opacity=1)
 return VGroup(disk,glow)


def lunar_phases(scene,stage='orbit'):
 """Consistent light, orbital position and Earth view, in one reusable shot."""
 stages={'new':0.,'first_quarter':PI/2,'full':PI,'last_quarter':3*PI/2}
 if stage not in {*stages,'orbit','half','summary'}:raise ValueError('Unknown lunar phase shot')
 p=palette(scene);portrait=config.frame_height>config.frame_width
 fg=p['foreground'];primary=p['primary'];lit='#DFAF45' if scene.lesson_style.get('theme')=='light' else '#F5D47F';dark='#293A52'
 labels=['新月','上弦','满月','下弦'];angles=[0,PI/2,PI,3*PI/2]
 if stage=='summary':
  centers=[[(-1 if i%2==0 else 1)*1.8,2.2-(i//2)*2.8,0] for i in range(4)] if portrait else [[(i-1.5)*3.05,.65,0] for i in range(4)]
  for i,(angle,center) in enumerate(zip(angles,centers)):
   disc=_phase_disc(angle,.67,center,lit,dark);label=scene.scene_text(labels[i],font_size=28,color=fg).move_to(np.array(center)+DOWN*1.05)
   scene.play(FadeIn(disc),FadeIn(label),run_time=.55)
  note=scene.scene_paragraph('月相：看到的亮面比例在变\n地球影子遮月：那是月食',width=config.frame_width*.82,font_size=28,color=primary).move_to([0,-1.65 if not portrait else -3.1,0]);scene.play(FadeIn(note),run_time=.6)
 else:
  center=np.array([0,2.6,0]) if portrait else np.array([-3.15,.1,0]);radius=1.42 if portrait else 1.65
  view=np.array([0,-2.2,0]) if portrait else np.array([3.45,.15,0])
  title=scene.scene_text('太空俯视',font_size=25,color=primary).move_to(center+UP*(radius+.48))
  eye=scene.scene_text('从地球看月亮',font_size=27,color=primary).move_to(view+UP*1.7)
  orbit=DashedVMobject(Circle(radius=radius,stroke_color=primary,stroke_width=1.3).move_to(center),num_dashes=36)
  earth=Circle(radius=.32,stroke_color=primary,stroke_width=2,fill_color=primary,fill_opacity=.22).move_to(center)
  earth_label=scene.scene_text('地球',font_size=22,color=fg).move_to(center+DOWN*.6)
  scene.add(title,eye,orbit,earth,earth_label)
  light_origin=center+RIGHT*(radius+1.4)
  for y in [-.42,0,.42]:
   scene.add(Arrow(light_origin+UP*y,light_origin+LEFT*.95+UP*y,buff=0,stroke_width=2.5,color=lit,max_tip_length_to_length_ratio=.16))
  sunlight=scene.scene_text('太阳光',font_size=22,color=primary).move_to(light_origin+LEFT*.45+UP*.85);scene.add(sunlight)
  angle=stages.get(stage,PI/2 if stage=='half' else 0.)
  moon=_phase_disc(PI/2,.22,center+radius*np.array([math.cos(angle),math.sin(angle),0]),lit,dark)
  observed=_phase_disc(angle,.88,view,lit,dark)
  label=scene.scene_text(labels[round(angle/(PI/2))%4],font_size=31,color=fg).move_to(view+DOWN*1.3)
  scene.play(FadeIn(moon),FadeIn(observed),FadeIn(label),run_time=.6)
  if stage=='orbit':
   previous=0.
   for target in [PI/2,PI,3*PI/2,2*PI]:
    origin=previous
    label.become(scene.scene_text('月相逐渐变化',font_size=27,color=fg).move_to(view+DOWN*1.3))
    def move(mob,alpha):
     a=origin+(target-origin)*alpha;mob.move_to(center+radius*np.array([math.cos(a),math.sin(a),0]))
    def illuminate(mob,alpha):mob.become(_phase_disc(origin+(target-origin)*alpha,.88,view,lit,dark))
    scene.play(UpdateFromAlphaFunc(moon,move),UpdateFromAlphaFunc(observed,illuminate),run_time=1.05,rate_func=linear)
    label.become(scene.scene_text(labels[round(target/(PI/2))%4],font_size=31,color=fg).move_to(view+DOWN*1.3));scene.wait(.35);previous=target
  if stage=='half':
   note=scene.scene_text('亮的一半始终朝向太阳',font_size=27,color=primary).move_to([0,-2.1 if not portrait else -.1,0]);scene.play(FadeIn(note),run_time=.4)
 note=scene.scene_paragraph('位置、大小不按比例 · 月相按北半球常见方向示意',width=config.frame_width*.87,font_size=17,color=fg).move_to([0,-2.55 if not portrait else -4.7,0]);scene.add(note);scene.wait(.5)
 return {'angle':stages.get(stage),'illuminated_fraction':None if stage not in stages else (1-math.cos(stages[stage]))/2}
