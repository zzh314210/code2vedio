import argparse
import json
import shutil
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
NARRATIONS = [
    "牛翻一倍，吃完时间就会减半吗？不一定，因为草还在长。两分钟，用动画讲清牛吃草。",
    "先统一单位：一头牛一天吃一份草。原有草量记作Ｑ。每天新长Ｇ份，Ｎ头牛每天吃Ｎ份。",
    "草库存，一边流入，一边流出。每天长Ｇ份，吃掉Ｎ份。真正减少的，是Ｎ减Ｇ份。",
    "原有草量，就是净消耗速度，乘上吃完的天数。Ｑ等于Ｎ减Ｇ，乘Ｔ。图上库存降到零，就是草吃完。",
    "来看一道例题：十头牛能吃二十二天，十六头牛能吃十天。换成二十五头牛，能吃几天？",
    "这两个方案，都从相同的原有草量出发。不是先吃二十二天，再换牛。两边的原有草量Ｑ，完全相同。",
    "第一种方案吃二百二十份，第二种吃一百六十份。多吃的六十份，对应多出来十二天的生长。相减，原有草量就抵消了。",
    "每天长草，六十除以十二，得到五份。原有草量，十减五，再乘二十二，等于一百一十份。用另一方案算，也相同。",
    "现在放入二十五头牛。等效理解：五头抵消新长的草，二十头消耗原有库存。每天净减少二十份。",
    "时间就是一百一十，除以二十，得到五点五天。五个整天，吃掉一百份。再加半天，吃掉最后十份。",
    "最后验算：总吃草量，是二十五乘五点五。原有一百一十份，加上新长二十七点五份。两边都是一百三十七点五份。",
    "记住三步：先求每天长草。再求原有草量。最后，用库存除以净消耗。牛吃草，本质就是动态库存。",
]
CAPTIONS = [
    "牛越多，时间就按比例减少吗？", "一头牛 · 一天 · 一份草", "净消耗 = 吃草 − 长草",
    "Q = (N − G) × T", "教学例题：25头牛能吃几天？", "两个独立方案，从相同 Q 开始",
    "多吃60份，对应多长12天", "G = 5份/天；Q = 110份", "25 − 5 = 20份/天",
    "5个整天 + 半天 = 5.5天", "25 × 5.5 = 110 + 5 × 5.5", "三步法：生长 → 库存 → 时间",
]
TITLES = ["牛吃草｜看懂动态库存", "一道例题｜先求生长与库存", "得出答案｜验证与三步法"]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def storyboard():
    return {"sections": [{
        "id": f"section_{section+1}", "title": TITLES[section], "icon_keywords": ["cow", "herb", "seedling", "sun"],
        "beats": [{"narration": NARRATIONS[beat], "caption": CAPTIONS[beat], "visual": f"可信浅色模板镜头 {beat+1}：{CAPTIONS[beat]}；横竖屏独立重排；真实彩色 SVG；比例严格按教材数据。"} for beat in range(section*4,section*4+4)],
    } for section in range(3)]}


def request(client, method, route, **kwargs):
    response = client.request(method, route, **kwargs)
    response.raise_for_status()
    return response.json()


def wait_job(client, job_id):
    last = None
    while True:
        job = request(client,"GET",f"/api/jobs/{job_id}")
        state = (job["status"],job.get("message"))
        if state != last:
            print(job_id, *state, flush=True)
            last = state
        if job["status"] not in ("queued","running"):
            if job["status"] in ("failed","error"):
                raise RuntimeError(job.get("error") or job.get("message") or "任务失败")
            return job
        time.sleep(3)


def seed_assets(output):
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    records = []
    for name in ("cow","herb","seedling","sun"):
        source = ROOT / "examples/assets/noto" / f"{name}.svg"
        destination = assets / source.name
        shutil.copy2(source,destination)
        records.append({"key":name,"path":str(destination.resolve()),"keyword":name,"id":f"noto:{name}","source":"Iconify public SVG API / Noto Emoji","credit":"Noto Emoji © Google · Apache-2.0","license":"Apache-2.0","url":f"https://api.iconify.design/noto/{name}.svg"})
    save(output / "assets.json",{"assets":records,"errors":[],"style":"Noto 彩色统一风格"})
    (output / "ATTRIBUTION.md").write_text("# 本片图标出处\n\nNoto Emoji，作者 Google Inc；Apache-2.0。通过免登录 Iconify 公共 SVG API 下载，未使用付费图片。\n\n" + "\n".join(f"- `{item['id']}`：{item['url']}" for item in records) + "\n\n许可原文随 examples/assets/noto/LICENSE-graphics.txt 提供。\n",encoding="utf-8")
    return records


def main():
    parser = argparse.ArgumentParser(description="可重复修改的牛吃草浅色V2制作；通过现有 Web 流水线，无模型生成费用")
    parser.add_argument("--parent",default="1ffb73363c20")
    parser.add_argument("--orientation",choices=("landscape","portrait"),default="landscape")
    parser.add_argument("--quality",choices=("low","high"),default="high")
    parser.add_argument("--job-id")
    parser.add_argument("--rate",default="+6%")
    parser.add_argument("--stop-after",choices=("audio","code","compose"),default="compose")
    args = parser.parse_args()
    with httpx.Client(base_url="http://127.0.0.1:8787",timeout=40) as client:
        token = request(client,"GET","/api/session")["csrf"]
        client.headers["X-C2V-CSRF"] = token
        if args.job_id:
            job_id = args.job_id
            state = request(client,"GET",f"/api/jobs/{job_id}")
            if state["status"] in ("queued","running"):
                wait_job(client,job_id)
        else:
            overrides = {"vision":{"enabled":False},"tts":{"provider":"edge","voice":"zh-CN-XiaoxiaoNeural","rate":args.rate},"video":{"quality":args.quality,"theme":"light","orientation":args.orientation,"brand":"行测可视化 · 数量关系","max_sections":3,"max_beats":4,"pause_seconds":0.28,"render_timeout":900,"fix_attempts":0},"course":{"instructions":"浅色精美V2；牛吃草动态库存；只讲一道教学例题；使用可信动画模板；不伪称历年真题。"}}
            result = request(client,"POST",f"/api/jobs/{args.parent}/rerun",json={"topic":"牛吃草 · 精美浅色 V2","config":overrides,"edit_name":"storyboard.json","edit_data":storyboard(),"stop_after":"storyboard","allow_generated_code":True})
            job_id = result["job_id"]
            print("VERSION",job_id,args.orientation,args.quality,flush=True)
            wait_job(client,job_id)
        output = ROOT / "workspace" / job_id / "output"
        records = seed_assets(output)
        for section in range(3):
            save(output / f"section_{section+1}_code.json",{"beats":[{"code":f"self.cow_grass({section*4+beat})"} for beat in range(4)]})
        request(client,"POST",f"/api/jobs/{job_id}/continue",json={"stop_after":"audio","allow_generated_code":True})
        wait_job(client,job_id)
        timed = json.loads((output / "timing.json").read_text(encoding="utf-8"))
        for section in timed["sections"]:
            section["assets"] = records
        save(output / "storyboard_assets.json",timed)
        duration = sum(beat["duration"] for section in timed["sections"] for beat in section["beats"])
        print("AUDIO_SECONDS",round(duration,3),"CUES",sum(len(beat.get("subtitles",[])) for section in timed["sections"] for beat in section["beats"]),flush=True)
        if args.stop_after != "audio":
            request(client,"POST",f"/api/jobs/{job_id}/continue",json={"stop_after":args.stop_after,"allow_generated_code":True})
            wait_job(client,job_id)
        save(output / "course_version.json",{"version":"V2-light","parent":args.parent,"orientation":args.orientation,"quality":args.quality,"duration":duration,"manual_review_required":True,"external_vision_review":"disabled; manual frame and math review required","template":"src/cow_grass_visuals.py","narration_script":"examples/create_cow_grass_v2.py"})
        print("OUTPUT",output,flush=True)


if __name__ == "__main__":
    main()
