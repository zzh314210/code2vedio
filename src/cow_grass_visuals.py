import numpy as np

from manim import (
    VGroup, Polygon, RoundedRectangle, Rectangle, Circle, Line, Arrow, UP,
    Text, ValueTracker, FadeIn, FadeOut, Transform,
    Indicate, AnimationGroup, LaggedStart, Create, config, linear,
)


INK = "#203C36"
MUTED = "#627A73"
TEAL = "#287D68"
GREEN = "#61A76E"
ORANGE = "#D88250"
MINT = "#E5F2EA"
PEACH = "#F9ECE2"


def label(scene, text, size=30, color=INK, width=None):
    result = scene.scene_text(text, size, color)
    if width and result.width > width:
        result.scale_to_fit_width(width)
    return result


def panel(width, height, color="#FFFFFF"):
    shadow = RoundedRectangle(width=width, height=height, corner_radius=0.18, stroke_width=0, fill_color="#DDE7DF", fill_opacity=0.6).shift([0.035, -0.05, 0])
    surface = RoundedRectangle(width=width, height=height, corner_radius=0.18, stroke_width=1, stroke_color="#DFEAE3", fill_color=color, fill_opacity=1)
    return VGroup(shadow, surface)


def pill(scene, text, width=3, color=MINT):
    return VGroup(panel(width, 0.56, color), label(scene, text, 22, TEAL, width - 0.3))


def icon(scene, name, height):
    return scene.asset(name).set_height(height)


def meadow(scene, width=5.4):
    top = Polygon([-2.8, -0.45, 0], [0.5, -1.15, 0], [2.8, 0.55, 0], [-0.5, 1.25, 0], stroke_color="#A8CEAD", stroke_width=1.4, fill_color="#CBE7CC", fill_opacity=1)
    front = Polygon([-2.8, -0.45, 0], [0.5, -1.15, 0], [0.5, -1.43, 0], [-2.8, -0.73, 0], stroke_width=0, fill_color="#A7CBA7", fill_opacity=1)
    side = Polygon([0.5, -1.15, 0], [2.8, 0.55, 0], [2.8, 0.27, 0], [0.5, -1.43, 0], stroke_width=0, fill_color="#91B795", fill_opacity=1)
    shadow = Polygon([-2.85, -0.8, 0], [0.55, -1.55, 0], [2.95, 0.23, 0], [-0.4, 1.0, 0], stroke_width=0, fill_color="#E0E7DF", fill_opacity=1)
    grass = VGroup(*[icon(scene, "herb", 0.42).move_to([horizontal, vertical, 0]) for horizontal, vertical in [(-2.0,-0.3),(-1.2,0.05),(-0.55,-0.65),(0.15,-0.24),(1.4,0.22),(2.0,0.53),(-0.6,0.72),(0.4,0.67)]])
    cows = VGroup(icon(scene, "cow", 0.9).move_to([-0.95,0.35,0]), icon(scene, "cow", 0.8).move_to([1.1,-0.25,0]))
    sun = icon(scene, "sun", 0.65).move_to([2.2, 1.65, 0])
    fence = VGroup()
    for horizontal, vertical in [(-2.5,-0.35),(-1.9,-0.48),(-1.3,-0.61)]:
        fence.add(Line([horizontal,vertical,0],[horizontal,vertical+0.35,0],color="#A5B4A3",stroke_width=3))
    fence.add(Line([-2.5,-0.13,0],[-1.3,-0.39,0],color="#A5B4A3",stroke_width=2))
    result = VGroup(shadow, front, side, top, fence, grass, cows, sun)
    result.scale_to_fit_width(width)
    return result, grass, cows


def at(scene, sentence, fallback=0.3):
    cues = scene.lesson_beats[scene._beat_index].get("subtitles", [])
    target = cues[sentence]["start"] if sentence < len(cues) else scene._beat_duration * fallback
    elapsed = scene.renderer.time - scene._beat_start
    scene.wait(max(0, target - elapsed))


def reveal(scene, *objects, duration=0.65):
    scene.play(LaggedStart(*[FadeIn(mob, shift=UP * 0.12) for mob in objects], lag_ratio=0.15), run_time=duration)


def flow(scene, origin, destination, color, count=4, duration=1.2):
    dots = VGroup(*[Circle(radius=0.055, stroke_width=0, fill_color=color, fill_opacity=1).move_to(origin) for number in range(count)])
    scene.add(dots)
    scene.play(LaggedStart(*[dot.animate.move_to(destination).set_opacity(0) for dot in dots], lag_ratio=0.18), run_time=duration)
    scene.remove(dots)


def stock(scene, width=5, amount=1):
    base = RoundedRectangle(width=width, height=0.52, corner_radius=0.12, stroke_width=0, fill_color="#DCEBE1", fill_opacity=1)
    fill = RoundedRectangle(width=width * amount, height=0.42, corner_radius=min(0.1, width * amount / 4), stroke_width=0, fill_color=TEAL, fill_opacity=1)
    fill.move_to([-(width - width * amount) / 2, 0, 0])
    return VGroup(base, fill)


def animate(scene, index):
    if not isinstance(index, int) or not 0 <= index < len(SCENES):
        raise ValueError("无效牛吃草课程镜头")
    SCENES[index](scene, scene.lesson_style.get("orientation") == "portrait")


def opening(scene, portrait):
    farm, grass, cows = meadow(scene, 6.1 if portrait else 6.5)
    farm.move_to([0 if portrait else -2.5, 1.6 if portrait else 0.05, 0])
    question = label(scene, "牛越多，就一定\n按比例更快吃完？", 42 if portrait else 38, width=6.2 if portrait else 5.1)
    question.move_to([0 if portrait else 3.0, -1.15 if portrait else 0.95, 0])
    reveal(scene, farm, question)
    at(scene, 1)
    hook = pill(scene, "关键：草一直在生长", 5.4)
    hook.move_to([0 if portrait else 3.0, -3.0 if portrait else -1.3, 0])
    reveal(scene, hook)
    scene.play(grass.animate.scale(1.2), cows.animate.shift([0.16, -0.04, 0]), run_time=1.0)
    scene.play(grass.animate.scale(1 / 1.2), cows.animate.shift([-0.16, 0.04, 0]), run_time=1.0)
    at(scene, 2, 0.68)
    scene.play(Indicate(hook, color=TEAL, scale_factor=1.04), run_time=0.8)


def units(scene, portrait):
    headline = pill(scene, "统一单位：1头牛 · 1天 · 1份草", 6.6)
    headline.move_to([0, 4.1 if portrait else 1.95, 0])
    reveal(scene, headline)
    terms = [("Q", "原有草量", "份", "herb", TEAL), ("G", "每天长草", "份 / 天", "seedling", GREEN), ("N", "每天吃草", "份 / 天", "cow", ORANGE)]
    cards = VGroup()
    for number, (symbol, title, unit, image, color) in enumerate(terms):
        width, height = (6.1, 1.85) if portrait else (3.35, 3.3)
        card = panel(width, height)
        if portrait:
            card.add(icon(scene,image,0.75).move_to([-2.2,0,0]), label(scene,symbol,45,color).move_to([-0.85,0.1,0]), label(scene,title,29).move_to([1.2,0.38,0]),label(scene,unit,22,MUTED).move_to([1.2,-0.4,0]))
            card.move_to([0, 2.25 - number * 2.2, 0])
        else:
            card.add(icon(scene,image,0.85).move_to([0,0.94,0]),label(scene,symbol,42,color).move_to([0,0.03,0]),label(scene,title,27).move_to([0,-0.71,0]),label(scene,unit,20,MUTED).move_to([0,-1.16,0]))
            card.move_to([-3.75 + number * 3.75, -0.15, 0])
        cards.add(card)
    at(scene, 1)
    reveal(scene, *cards, duration=1.15)
    scene.play(Indicate(cards[0],color=TEAL,scale_factor=1.03),run_time=0.6)
    at(scene, 2, 0.6)
    scene.play(Indicate(cards[1],color=GREEN,scale_factor=1.03),Indicate(cards[2],color=ORANGE,scale_factor=1.03),run_time=0.8)


def net_rate(scene, portrait):
    farm, grass, cows = meadow(scene, 5.8 if portrait else 4.5)
    farm.move_to([0 if portrait else -3.5,2.2 if portrait else 0.35,0])
    meter = stock(scene,5.7 if portrait else 4.5)
    meter.move_to([0 if portrait else 3.1,-0.8 if portrait else 0.2,0])
    growing = label(scene,"长出 G",27,GREEN).move_to([-2.0 if portrait else 1.8,0.45 if portrait else 1.6,0])
    eating = label(scene,"吃掉 N",27,ORANGE).move_to([2.0 if portrait else 4.5,0.45 if portrait else 1.6,0])
    reveal(scene,farm,meter,growing,eating)
    start = meter.get_left() + np.array([0,0.65,0])
    finish = meter.get_right() + np.array([0,0.65,0])
    flow(scene,start,meter.get_center(),GREEN)
    at(scene,1)
    flow(scene,meter.get_center(),finish,ORANGE)
    reduced = stock(scene,5.7 if portrait else 4.5,0.64).move_to(meter.get_center())
    scene.play(Transform(meter,reduced),grass.animate.scale(1.1),run_time=1.0)
    at(scene,2,0.65)
    equation = label(scene,"净减少 = N − G",38,TEAL,width=6.1)
    equation.move_to([0,-3.0 if portrait else -1.75,0])
    reveal(scene,equation)
    scene.play(Indicate(equation,color=TEAL,scale_factor=1.04),run_time=0.8)


def principle(scene, portrait):
    formula = label(scene,"Q = (N − G) × T",43,TEAL,width=6.4 if portrait else 10)
    formula.move_to([0,3.5 if portrait else 1.85,0])
    reveal(scene,formula)
    left = np.array([-2.55 if portrait else -4.0,0.0 if portrait else -1.6,0])
    right = left + np.array([5.1 if portrait else 8.0,0,0])
    high = left + np.array([0,2.15,0])
    axes = VGroup(Arrow(left,right+[0.3,0,0],buff=0,color=MUTED,stroke_width=2),Arrow(left,high+[0,0.4,0],buff=0,color=MUTED,stroke_width=2))
    axis_labels = VGroup(label(scene,"Q",24,TEAL).move_to(high+[-0.3,0.05,0]),label(scene,"0",22,MUTED).move_to(left+[-0.24,-0.24,0]),label(scene,"T 天",23,MUTED).move_to(right+[0,-0.35,0]))
    reveal(scene,axes,axis_labels)
    descending = Line(high,right,color=TEAL,stroke_width=5)
    marker = Circle(radius=0.09,fill_color=TEAL,fill_opacity=1,stroke_width=0).move_to(high)
    scene.add(marker)
    scene.play(Create(descending),marker.animate.move_to(right),run_time=2.2,rate_func=linear)
    at(scene,1)
    note = pill(scene,"库存 = 每天净减少 × 天数",6.5)
    note.move_to([0,-2.05 if portrait else -2.35,0])
    reveal(scene,note)
    at(scene,2,0.7)
    scene.play(Indicate(formula,color=TEAL,scale_factor=1.04),run_time=0.8)


def example(scene, portrait):
    banner = pill(scene,"同一牧场 · 草匀速生长 · 牛食量相同",6.6)
    banner.move_to([0,4.2 if portrait else 2.0,0])
    reveal(scene,banner)
    conditions = [("10头", "22天",TEAL), ("16头","10天",TEAL), ("25头","几天？",ORANGE)]
    cards = VGroup()
    for number,(amount,days,color) in enumerate(conditions):
        width,height = (6.0,1.85) if portrait else (3.5,3.3)
        card = panel(width,height,PEACH if number==2 else "#FFFFFF")
        if portrait:
            card.add(icon(scene,"cow",0.8).move_to([-2.05,0,0]),label(scene,amount,36,color).move_to([-0.45,0,0]),label(scene,days,36,color).move_to([1.65,0,0]))
            card.move_to([0,2.3-number*2.2,0])
        else:
            card.add(icon(scene,"cow",0.85).move_to([0,0.8,0]),label(scene,amount,36,color).move_to([0,-0.1,0]),label(scene,days,38,color).move_to([0,-1.0,0]))
            card.move_to([-3.8+number*3.8,-0.25,0])
        cards.add(card)
    reveal(scene,cards[0],cards[1],duration=0.9)
    at(scene,1)
    reveal(scene,cards[2])
    footer = label(scene,"教学例题 · 非历年真题",19,MUTED)
    footer.move_to([0,-4.0 if portrait else -2.35,0])
    reveal(scene,footer)
    scene.play(Indicate(cards[2],color=ORANGE,scale_factor=1.03),run_time=0.75)


def same_start(scene, portrait):
    heading = pill(scene,"两个独立假设：都从相同 Q 出发",6.6)
    heading.move_to([0,4.25 if portrait else 2.0,0])
    reveal(scene,heading)
    cards = VGroup()
    for number,(amount,days) in enumerate([(10,22),(16,10)]):
        width,height = (6.2,2.9) if portrait else (5.25,3.25)
        card = panel(width,height)
        card.add(label(scene,f"方案 {'A' if number==0 else 'B'} · {amount}头",28,TEAL).move_to([0,1.02,0]))
        card.add(stock(scene,4.1).move_to([0,0.35,0]),label(scene,"相同原有草量 Q",21,MUTED).move_to([0,-0.2,0]))
        card.add(label(scene,f"({amount} − G) × {days} = Q",29,TEAL,width=4.6).move_to([0,-0.93,0]))
        card.move_to([0,2.1-number*3.5,0] if portrait else [-2.9+number*5.8,-0.2,0])
        cards.add(card)
    reveal(scene,*cards)
    at(scene,1)
    note = label(scene,"不是先吃22天，再换成16头牛",25,ORANGE,width=6.5 if portrait else 11)
    note.move_to([0,-4.3 if portrait else -2.3,0])
    reveal(scene,note)
    scene.play(Indicate(cards[0],color=TEAL,scale_factor=1.02),Indicate(cards[1],color=TEAL,scale_factor=1.02),run_time=0.8)


def differences(scene, portrait):
    width = 5.9 if portrait else 9.0
    left = -width / 2
    top_y = 2.55 if portrait else 0.95
    lower_y = top_y - 1.6
    base_width = width * 160 / 220
    extra_width = width * 60 / 220
    first = VGroup(Rectangle(width=base_width,height=0.52,stroke_width=0,fill_color=TEAL,fill_opacity=1).move_to([left+base_width/2,top_y,0]),Rectangle(width=extra_width,height=0.52,stroke_width=0,fill_color=GREEN,fill_opacity=1).move_to([left+base_width+extra_width/2,top_y,0]))
    second = Rectangle(width=base_width,height=0.52,stroke_width=0,fill_color=TEAL,fill_opacity=1).move_to([left+base_width/2,lower_y,0])
    text_first = label(scene,"10 × 22 = 220份",28,TEAL).move_to([0,top_y+0.63,0])
    text_second = label(scene,"16 × 10 = 160份",28,TEAL).move_to([0,lower_y+0.63,0])
    reveal(scene,text_first,first,text_second,second)
    at(scene,1)
    extra = label(scene,"多吃 60份",25,GREEN).move_to([left+base_width+extra_width/2,top_y-0.64,0])
    reveal(scene,extra)
    scene.play(Indicate(first[1],color=GREEN,scale_factor=1.06),run_time=0.7)
    at(scene,2,0.65)
    time = pill(scene,"多长 22 − 10 = 12天",6.0)
    time.move_to([0,-1.55 if portrait else -1.72,0])
    cancellation = label(scene,"相同 Q 抵消 → 60 = 12 × G",26,TEAL,width=6.5 if portrait else 11)
    cancellation.move_to([0,-3.05 if portrait else -2.5,0])
    reveal(scene,time,cancellation)


def recover(scene, portrait):
    first = panel(6.35 if portrait else 10.2,2.05)
    first.add(icon(scene,"seedling",0.7).move_to([-2.45 if portrait else -4.25,0,0]))
    first.add(label(scene,"G = 60 ÷ 12 = 5",36,GREEN,width=4.8 if portrait else 8).move_to([0.45,0.25,0]),label(scene,"每天新长 5份",24,MUTED).move_to([0.45,-0.55,0]))
    first.move_to([0,2.25 if portrait else 1.1,0])
    reveal(scene,first)
    at(scene,1)
    second = panel(6.35 if portrait else 10.2,2.05)
    second.add(icon(scene,"herb",0.7).move_to([-2.45 if portrait else -4.25,0,0]))
    second.add(label(scene,"Q = (10 − 5) × 22",32,TEAL,width=4.9 if portrait else 8).move_to([0.45,0.38,0]),label(scene,"= 110份原有草",31,TEAL).move_to([0.45,-0.43,0]))
    second.move_to([0,-0.5 if portrait else -1.3,0])
    reveal(scene,second)
    at(scene,2,0.7)
    cross = label(scene,"另一方案：(16 − 5) × 10 = 110",24,MUTED,width=6.35 if portrait else 11)
    cross.move_to([0,-3.05 if portrait else -2.63,0])
    reveal(scene,cross)


def equivalent(scene, portrait):
    cows = VGroup()
    for number in range(25):
        row,column = divmod(number,5)
        horizontal = (column-2)*0.87
        vertical = 1.7-row*0.64
        cow = icon(scene,"cow",0.45).move_to([horizontal,vertical,0])
        backing = RoundedRectangle(width=0.73,height=0.57,corner_radius=0.1,stroke_width=0,fill_color=MINT if row==0 else PEACH,fill_opacity=1).move_to(cow.get_center())
        cows.add(VGroup(backing,cow))
    cows.move_to([0 if portrait else -3.0,1.8 if portrait else 0,0])
    reveal(scene,cows,duration=1.05)
    total = label(scene,"25头牛",32,INK).move_to([0 if portrait else -3.0,4.0 if portrait else 1.96,0])
    reveal(scene,total)
    at(scene,1)
    green = pill(scene,"5头抵消新草",4.5,MINT)
    orange = pill(scene,"20头消耗原有草",4.5,PEACH)
    green.move_to([0 if portrait else 3.1,-0.65 if portrait else 0.92,0])
    orange.move_to([0 if portrait else 3.1,-1.65 if portrait else -0.12,0])
    reveal(scene,green,orange)
    scene.play(Indicate(VGroup(*cows[:5]),color=GREEN,scale_factor=1.03),run_time=0.7)
    at(scene,2,0.67)
    formula = label(scene,"净消耗 = 25 − 5 = 20份/天",31,TEAL,width=6.35 if portrait else 11)
    formula.move_to([0,-3.4 if portrait else -2.06,0])
    note = label(scene,"等效分组，不是指定哪5头牛",20,MUTED,width=6.2 if portrait else 11)
    note.move_to([0,-4.3 if portrait else -2.63,0])
    reveal(scene,formula,note)


def answer(scene, portrait):
    formula = label(scene,"T = 110 ÷ 20 = 5.5天",42,TEAL,width=6.5 if portrait else 11)
    formula.move_to([0,3.9 if portrait else 1.9,0])
    reveal(scene,formula)
    meter_width = 5.9 if portrait else 10.3
    meter_y = 2.0 if portrait else 0.55
    background = stock(scene,meter_width)
    background.move_to([0,meter_y,0])
    amount = ValueTracker(110)
    fill = background[1]
    initial = fill.copy()
    fill.add_updater(lambda mob: mob.become(initial.copy().stretch(max(0.0001,amount.get_value()/110),0,about_point=initial.get_left())))
    number = label(scene,"库存 110份",30,TEAL).move_to([0,meter_y+0.66,0])
    reveal(scene,background,number)
    cells = VGroup()
    cell_width = 1.05 if portrait else 1.65
    for day in range(6):
        half = day==5
        width = cell_width * (0.5 if half else 1)
        cell = panel(width,1.0,PEACH if half else MINT)
        cell.add(label(scene,"半天" if half else f"第{day+1}天",14 if half else 17,TEAL,width-0.12).move_to([0,0.2,0]),label(scene,"10份" if half else "20份",14 if half else 18,MUTED,width-0.12).move_to([0,-0.23,0]))
        if portrait:
            cell.move_to([-1.6+(day%3)*1.6, -0.15-(day//3)*1.45,0])
        else:
            cell.move_to([-4.55+day*1.82-(0.4125 if half else 0),-0.9,0])
        cell.set_opacity(0.15)
        cells.add(cell)
    scene.add(cells)
    at(scene,1)
    for day in range(5):
        remaining = 110 - (day + 1) * 20
        updated_number = label(scene,f"库存 {remaining}份",30,TEAL).move_to(number.get_center())
        scene.play(cells[day].animate.set_opacity(1),amount.animate.set_value(remaining),Transform(number,updated_number),run_time=0.55,rate_func=linear)
    at(scene,2,0.73)
    updated_number = label(scene,"库存 0份",30,TEAL).move_to(number.get_center())
    scene.play(cells[5].animate.set_opacity(1),amount.animate.set_value(0),Transform(number,updated_number),run_time=0.6,rate_func=linear)
    amount.set_value(0)
    fill.clear_updaters()
    note = pill(scene,"5个整天 + 半天 = 5.5天",6.4)
    note.move_to([0,-3.6 if portrait else -2.35,0])
    reveal(scene,note)


def verification(scene, portrait):
    width = 6.0 if portrait else 9.6
    top_y = 2.6 if portrait else 0.85
    bottom_y = 0.4 if portrait else -1.1
    left = -width/2
    consuming = Rectangle(width=width,height=0.58,stroke_width=0,fill_color=ORANGE,fill_opacity=1).move_to([0,top_y,0])
    original = Rectangle(width=width*0.8,height=0.58,stroke_width=0,fill_color=TEAL,fill_opacity=1).move_to([left+width*0.4,bottom_y,0])
    growth = Rectangle(width=width*0.2,height=0.58,stroke_width=0,fill_color=GREEN,fill_opacity=1).move_to([left+width*0.9,bottom_y,0])
    first = label(scene,"总吃草：25 × 5.5 = 137.5",29,ORANGE,width=6.4 if portrait else 11).move_to([0,top_y+0.75,0])
    reveal(scene,first,consuming)
    at(scene,1)
    second = label(scene,"原有110 + 新长27.5 = 137.5",27,TEAL,width=6.4 if portrait else 11).move_to([0,bottom_y+0.75,0])
    reveal(scene,second,original,growth)
    parts = VGroup(label(scene,"110",24,"#FFFFFF").move_to(original.get_center()),label(scene,"27.5",20,"#FFFFFF").move_to(growth.get_center()))
    reveal(scene,parts)
    at(scene,2,0.65)
    success = pill(scene,"吃掉的草 = 原有草 + 新长草",6.5)
    success.move_to([0,-2.65 if portrait else -2.45,0])
    reveal(scene,success)
    scene.play(Indicate(success,color=TEAL,scale_factor=1.03),run_time=0.7)


def takeaway(scene, portrait):
    rows = [("01","求生长 G","差草量 ÷ 差天数"),("02","求库存 Q","(牛数 − G) × 天数"),("03","求时间 T","Q ÷ (新牛数 − G)")]
    cards = VGroup()
    for number,(step,title,detail) in enumerate(rows):
        width,height = (6.3,1.8) if portrait else (3.55,3.0)
        card = panel(width,height)
        if portrait:
            card.add(label(scene,step,34,GREEN).move_to([-2.35,0,0]),label(scene,title,29,TEAL).move_to([0.45,0.4,0]),label(scene,detail,23,MUTED,width=4.5).move_to([0.45,-0.42,0]))
            card.move_to([0,2.8-number*2.1,0])
        else:
            card.add(label(scene,step,28,GREEN).move_to([0,0.95,0]),label(scene,title,30,TEAL).move_to([0,0.05,0]),label(scene,detail,21,MUTED,width=3.1).move_to([0,-0.88,0]))
            card.move_to([-3.85+number*3.85,0.1,0])
        cards.add(card)
    reveal(scene,cards[0])
    at(scene,1)
    reveal(scene,cards[1])
    at(scene,2,0.56)
    reveal(scene,cards[2])
    at(scene,3,0.76)
    finish = pill(scene,"牛吃草，本质就是动态库存",6.4)
    finish.move_to([0,-4.15 if portrait else -2.24,0])
    reveal(scene,finish)


SCENES = [opening, units, net_rate, principle, example, same_start, differences, recover, equivalent, answer, verification, takeaway]
