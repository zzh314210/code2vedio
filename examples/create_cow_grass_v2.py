import argparse
import json
import shutil
from pathlib import Path

import sys


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
    sys.path.insert(0, str(ROOT / "src"))
    from configuration import load_config, merge, resolve_config
    from pipeline import VideoPipeline, save_json
    from video_project import apply_project_pack, archive_resource, initialize_project, new_project_path, project_pack_config, restore_project_config

    parser = argparse.ArgumentParser(description="牛吃草独立项目示例：固定教案和可信动画，不调用文本或视觉模型；配音仍需 TTS 服务")
    parser.add_argument("--config")
    parser.add_argument("--project")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--orientation", choices=("landscape", "portrait"), default="landscape")
    parser.add_argument("--quality", choices=("low", "high"), default="high")
    parser.add_argument("--rate", default="+6%")
    parser.add_argument("--stop-after", choices=("audio", "code", "compose"), default="compose")
    parser.add_argument("--allow-generated-code", action="store_true")
    args = parser.parse_args()
    if args.stop_after == "compose" and not args.allow_generated_code:
        parser.error("渲染项目扩展会执行 Python，请明确传入 --allow-generated-code")
    if args.resume and not args.project:
        parser.error("续跑请指定 --project")
    topic = "牛吃草 · 精美浅色 V2"
    project = Path(args.project).resolve() if args.project else new_project_path(topic)
    config = load_config(args.config)
    pack = ROOT / "examples/video_project/cow_grass"
    if args.resume:
        if not (project / "settings.json").is_file():
            parser.error("指定项目没有配置快照，不能续跑")
        config = resolve_config(restore_project_config(project, config))
    else:
        if project.exists():
            parser.error("项目目录已存在，请使用新目录或 --resume")
        config = resolve_config(merge(merge(config, project_pack_config(pack)), {
            "vision": {"enabled": False},
            "tts": {"provider": "edge", "voice": "zh-CN-XiaoxiaoNeural", "rate": args.rate},
            "video": {"quality": args.quality, "orientation": args.orientation, "max_sections": 3, "max_beats": 4, "pause_seconds": 0.28, "render_timeout": 900, "fix_attempts": 0},
        }))
        initialize_project(project, topic, config)
        apply_project_pack(pack, project)
        archive_resource(project, Path(__file__).name, Path(__file__).read_bytes())
    output = project / "output"
    materials = [] if args.resume else sorted((project / "materials").glob("*.md"))
    pipeline = VideoPipeline(topic, config, output, materials, resume=args.resume, project=project)
    if not args.resume:
        source = pipeline.materials["selected_chunks"][0]["source"]
        save_json(output / "outline.json", {"topic": topic, "target_audience": "行测数量关系初学者", "warnings": [], "sections": [
            {"id": f"section_{index+1}", "title": title, "goal": title, "key_points": [title], "sources": [source]} for index, title in enumerate(TITLES)
        ]})
        save_json(output / "storyboard.json", storyboard())
        seed_assets(output)
        for section in range(3):
            save_json(output / f"section_{section+1}_code.json", {"beats": [
                {"code": f'self.extension("cow_grass", {section*4+beat})'} for beat in range(4)
            ]})
    pipeline.run(stop_after="audio")
    timed = json.loads((output / "timing.json").read_text(encoding="utf-8"))
    if not (output / "storyboard_assets.json").exists():
        records = json.loads((output / "assets.json").read_text(encoding="utf-8"))["assets"]
        for section in timed["sections"]:
            section["assets"] = records
        save_json(output / "storyboard_assets.json", timed)
    duration = sum(beat["duration"] for section in timed["sections"] for beat in section["beats"])
    if args.stop_after != "audio":
        pipeline.run(stop_after=args.stop_after)
    save_json(output / "course_version.json", {"version": "V2-light", "orientation": config["video"]["orientation"], "quality": config["video"]["quality"], "duration": duration, "manual_review_required": True, "external_vision_review": "disabled; manual frame and math review required", "template": "code/runtime/extensions/cow_grass.py", "narration_script": "code/svg/create_cow_grass_v2.py"})
    print("PROJECT", project, "AUDIO_SECONDS", round(duration, 3), flush=True)


if __name__ == "__main__":
    main()
