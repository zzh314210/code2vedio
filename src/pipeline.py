import ast
import hashlib
import json
import math
import os
import re
import sys
import textwrap
from pathlib import Path

from configuration import public_config, sanitize_error
from lesson_prompts import outline_prompt, storyboard_prompt, code_prompt, review_prompt
from materials import load_materials
from media import concat, fit_audio, mux, probe, run_command, sample_frames, write_subtitles
from model_gateway import ModelGateway
from narration import Narrator
from icon_assets import AssetManager


def save_json(filename, value):
    temporary = filename.with_suffix(filename.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(filename)


def nonempty(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} 必须是非空字符串且不超过 {maximum} 字")


def validate_snippet(code):
    nonempty(code, "Manim code", 24000)
    tree = ast.parse(code)
    prohibited = (ast.Import, ast.ImportFrom, ast.While, ast.With, ast.AsyncWith, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Return, ast.Raise, ast.Try, ast.Global, ast.Nonlocal)
    denied_names = {"open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals", "vars", "input", "breakpoint", "__import__", "Tex", "MathTex", "SVGMobject", "ImageMobject"}
    allowed_methods = {"play", "wait", "add", "remove", "scene_text", "asset", "cow_grass"}
    for node in ast.walk(tree):
        if isinstance(node, prohibited):
            raise ValueError("代码片段不能包含 import/while/with/类/函数/异常控制")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in denied_names):
            raise ValueError(f"不允许的代码标识符: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError("代码不能访问私有/反射属性")
            if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr not in allowed_methods:
                raise ValueError(f"不允许访问 self.{node.attr}")
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                raise ValueError("不能修改对象属性，请使用 Manim 方法")


def validate_code(value, count):
    if not isinstance(value, dict) or not isinstance(value.get("beats"), list) or len(value["beats"]) != count:
        raise ValueError(f"代码必须包含 {count} 个 beats")
    for beat in value["beats"]:
        validate_snippet(beat["code"])


STAGES = ["outline", "storyboard", "audio", "assets", "code", "render", "review", "compose"]


def task_fingerprint(topic, config, materials):
    payload = {"version": 1, "topic": topic, "config": config, "sources": materials["sources"], "context": materials["context"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class VideoPipeline:
    def __init__(self, topic, config, output, materials=None, pages=None, resume=False, on_event=None):
        self.topic = topic
        self.config = config
        self.on_event = on_event or (lambda event: None)
        self.active_stage = None
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.materials = load_materials(materials or [], topic, config["materials"], pages)
        self.text = ModelGateway(config["text"])
        self.vision = ModelGateway(config["vision"], "vision") if config["vision"]["enabled"] else None
        self.narrator = Narrator(config["tts"])
        self.assets = AssetManager(config["assets"], self.output)
        public = public_config(config)
        fingerprint = task_fingerprint(topic, public, self.materials)
        manifest = self.output / "manifest.json"
        vision_changed = False
        if manifest.exists():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if not resume:
                raise ValueError("输出目录已存在任务；请使用新目录或 --resume")
            if existing["fingerprint"] != fingerprint:
                previous_config = {**public, "vision": existing.get("config", {}).get("vision", {})}
                vision_changed = task_fingerprint(topic, previous_config, self.materials) == existing["fingerprint"]
                if not vision_changed:
                    raise ValueError("模型/教材/配置与缓存不一致，请使用新输出目录，避免复用过期教案/配音")
                for stale_review in (self.output / "reviewed.json", *self.output.glob("*_review_*.json")):
                    stale_review.unlink(missing_ok=True)
        self.manifest = {"fingerprint": fingerprint, "topic": topic, "config": public, "status": "started", "stages": {}}
        if resume and manifest.exists():
            self.manifest["stages"] = existing.get("stages", {})
        if vision_changed:
            for stage in ("review", "compose"):
                self.manifest["stages"].pop(stage, None)
        save_json(manifest, self.manifest)
        save_json(self.output / "materials.json", self.materials)
        if self.materials["omitted_chunks"]:
            print(f"教材超过上下文预算，已选取相关片段；省略 {self.materials['omitted_chunks']} 段，详见 materials.json")

    def cached_json(self, filename, prompt, validator):
        file = self.output / filename
        if file.exists():
            result = json.loads(file.read_text(encoding="utf-8"))
            validator(result)
            return result
        result = self.text.json(prompt, validator)
        save_json(file, result)
        return result

    def prompt(self, stage, original):
        course = self.config.get("course", {})
        return original + f"\n创作者课程要求（仍须符合事实和输出格式约束）：{course.get('instructions', '')}\n本阶段补充要求：{course.get('prompts', {}).get(stage, '')}"

    def event(self, stage, status, message=""):
        self.active_stage = stage
        event = {"stage": stage, "status": status, "message": sanitize_error(message, self.config)}
        self.manifest["stages"][stage] = event
        save_json(self.output / "manifest.json", self.manifest)
        self.on_event(event)

    def validate_outline(self, outline):
        if not isinstance(outline, dict):
            raise ValueError("大纲必须是 JSON 对象")
        nonempty(outline["topic"], "topic")
        nonempty(outline["target_audience"], "target_audience")
        if not isinstance(outline.get("warnings"), list) or not all(isinstance(item, str) for item in outline["warnings"]):
            raise ValueError("warnings 必须为字符串数组")
        sections = outline["sections"]
        if not isinstance(sections, list) or not 1 <= len(sections) <= self.config["video"]["max_sections"]:
            raise ValueError("大纲章节数量超出限制")
        valid_sources = {chunk["source"] for chunk in self.materials["selected_chunks"]}
        for index, section in enumerate(sections, 1):
            if section["id"] != f"section_{index}":
                raise ValueError("章节 ID 必须按顺序为 section_1、section_2 等")
            nonempty(section["title"], "title", 60)
            nonempty(section["goal"], "goal")
            if not isinstance(section["key_points"], list) or not section["key_points"]:
                raise ValueError("章节缺少 key_points")
            for point in section["key_points"]:
                nonempty(point, "key_point")
            if not isinstance(section["sources"], list) or any(source not in valid_sources for source in section["sources"]):
                raise ValueError("来源必须是教材中的完整标签，不能虚构引用")
            if valid_sources and not section["sources"]:
                raise ValueError("提供教材时，每章必须标注至少一个教材来源")

    def validate_storyboard(self, storyboard, outline):
        sections = storyboard["sections"]
        if not isinstance(sections, list) or len(sections) != len(outline["sections"]):
            raise ValueError("分镜与大纲章节数量不一致")
        for section, original in zip(sections, outline["sections"]):
            if section["id"] != original["id"]:
                raise ValueError("分镜章节顺序/ID 必须与大纲相同")
            nonempty(section["title"], "title", 60)
            if not isinstance(section["beats"], list) or not 1 <= len(section["beats"]) <= self.config["video"]["max_beats"]:
                raise ValueError("分镜 beats 数量超出限制")
            for beat in section["beats"]:
                nonempty(beat["narration"], "narration", 140)
                nonempty(beat["caption"], "caption", 42)
                nonempty(beat["visual"], "visual")
            keywords = section.get("icon_keywords", [])
            if not isinstance(keywords, list) or len(keywords) > 4 or any(not isinstance(term, str) or not re.fullmatch(r"[a-zA-Z0-9 -]{1,50}", term) for term in keywords):
                raise ValueError("icon_keywords 必须是最多 4 个简单英文关键词")

    def prepare(self):
        print("[1/6] 生成教材约束的中文教学大纲")
        outline = self.cached_json("outline.json", outline_prompt(self.topic, self.materials, self.config["video"]), self.validate_outline)
        print("[2/6] 生成逐句旁白和动画分镜")
        storyboard = self.cached_json("storyboard.json", storyboard_prompt(outline, self.materials, self.config["video"]), lambda value: self.validate_storyboard(value, outline))
        for warning in outline["warnings"]:
            print(f"内容核验提示: {warning}")
        return outline, storyboard

    def prepare_audio(self, section):
        fps = self.config["video"]["fps"]
        for index, beat in enumerate(section["beats"]):
            audio = self.output / "audio" / f"{section['id']}_{index + 1:02}.wav"
            metadata = audio.with_suffix(".json")
            audio_fingerprint = hashlib.sha256(json.dumps({"text": beat["narration"], "tts": public_config(self.config["tts"]), "subtitle_version": 2}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if audio.is_file() and metadata.is_file():
                info = json.loads(metadata.read_text(encoding="utf-8"))
                if info.get("fingerprint") != audio_fingerprint:
                    info = self.narrator.synthesize(beat["narration"], audio)
                    info["fingerprint"] = audio_fingerprint
                    save_json(metadata, info)
                probe(audio)
            else:
                info = self.narrator.synthesize(beat["narration"], audio)
                info["fingerprint"] = audio_fingerprint
                save_json(metadata, info)
            beat["duration"] = math.ceil((info["duration"] + self.config["video"]["pause_seconds"]) * fps) / fps
            beat["audio"] = str(audio)
            beat["subtitles"] = info.get("subtitles", [])
        return section

    def assemble_code(self, section, snippets):
        definitions = "from manim import *\nimport numpy as np\nimport math\nfrom scene_runtime import NarratedScene\n\n"
        style = {key: self.config["video"].get(key) for key in ("theme", "orientation", "brand")}
        background = "#F7FAF7" if style["theme"] == "light" else "#0b1020"
        definitions += f"config.background_color = {background!r}\n"
        if style["orientation"] == "portrait":
            definitions += "config.frame_width = 8\nconfig.frame_height = 14.2222222222\n"
        definitions += "\nclass LessonScene(NarratedScene):\n"
        definitions += f"    lesson_style = {style!r}\n"
        definitions += f"    lesson_title = {section['title']!r}\n    lesson_font = {self.config['video']['font']!r}\n"
        definitions += f"    lesson_beats = {section['beats']!r}\n\n    def construct(self):\n"
        asset_paths = {item["key"]: item["path"] for item in section.get("assets", [])}
        credits = " | ".join(sorted({item["credit"] for item in section.get("assets", [])}))
        definitions = definitions.replace("\n\n    def construct(self):", f"\n    lesson_assets = {asset_paths!r}\n    lesson_credits = {credits!r}\n\n    def construct(self):")
        for index, beat in enumerate(snippets["beats"]):
            definitions += f"        self.begin_beat({index})\n"
            definitions += textwrap.indent(beat["code"].strip(), "        ") + "\n"
            definitions += "        self.end_beat()\n"
        ast.parse(definitions)
        return definitions

    def render(self, section, snippets, revision):
        directory = self.output / section["id"] / f"revision_{revision}"
        directory.mkdir(parents=True, exist_ok=True)
        script = directory / "scene.py"
        script.write_text(self.assemble_code(section, snippets), encoding="utf-8")
        quality = {"low": "-ql", "medium": "-qm", "high": "-qh"}[self.config["video"]["quality"]]
        arguments = [sys.executable, "-m", "manim", quality, "--renderer", "cairo", "--fps", str(self.config["video"]["fps"]), "--disable_caching", "--media_dir", str(directory / "media"), "--output_file", "lesson", str(script), "LessonScene"]
        if self.config["video"].get("orientation") == "portrait":
            arguments[3:3] = ["--resolution", "1080,1920" if self.config["video"]["quality"] == "high" else "540,960"]
        previous_path = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = str(Path(__file__).parent) + (os.pathsep + previous_path if previous_path else "")
        try:
            output = run_command(arguments, timeout=self.config["video"]["render_timeout"])
            (directory / "render.log").write_text(output, encoding="utf-8")
        except RuntimeError as failure:
            (directory / "render.log").write_text(str(failure), encoding="utf-8")
            raise
        finally:
            if previous_path:
                os.environ["PYTHONPATH"] = previous_path
            else:
                os.environ.pop("PYTHONPATH", None)
        matches = list((directory / "media").rglob("lesson.mp4"))
        if len(matches) != 1:
            raise RuntimeError("Manim 未生成唯一 lesson.mp4")
        video = matches[0]
        expected = sum(beat["duration"] for beat in section["beats"])
        if abs(probe(video)["duration"] - expected) > max(0.12, 2 / self.config["video"]["fps"]):
            raise RuntimeError("动画时间轴与旁白时长不一致，需要修复代码")
        return video

    def render_with_repairs(self, section, snippets, start_revision):
        for attempt in range(self.config["video"]["fix_attempts"] + 1):
            revision = start_revision + attempt
            save_json(self.output / f"{section['id']}_code_{revision}.json", snippets)
            try:
                return self.render(section, snippets, revision), snippets, revision
            except RuntimeError as failure:
                if attempt == self.config["video"]["fix_attempts"]:
                    raise RuntimeError(f"{section['id']} 渲染修复耗尽，完整日志已保存") from failure
                print(f"修复 {section['id']}，第 {attempt + 1} 次")
                snippets = self.text.json(self.prompt("code", code_prompt(section, snippets, str(failure)[-8000:])), lambda value: validate_code(value, len(section["beats"])))

    def run(self, plan_only=False, stop_after="compose"):
        try:
            if plan_only:
                stop_after = "storyboard"
            if stop_after not in STAGES:
                raise ValueError("无效流水线阶段")
            self.event("outline", "running", "生成教材约束的中文教学大纲")
            outline = self.cached_json("outline.json", self.prompt("outline", outline_prompt(self.topic, self.materials, self.config["video"])), self.validate_outline)
            self.event("outline", "complete")
            for warning in outline["warnings"]:
                print(f"内容核验提示: {warning}")
            if stop_after == "outline":
                return self.output / "outline.json"
            self.event("storyboard", "running", "生成逐句旁白和动画分镜")
            storyboard = self.cached_json("storyboard.json", self.prompt("storyboard", storyboard_prompt(outline, self.materials, self.config["video"])), lambda value: self.validate_storyboard(value, outline))
            self.event("storyboard", "complete")
            if stop_after == "storyboard":
                return self.output / "storyboard.json"
            self.event("audio", "running", "合成旁白并测量真实时长")
            for section in storyboard["sections"]:
                section = self.prepare_audio(section)
                save_json(self.output / f"{section['id']}_timing.json", section)
            save_json(self.output / "timing.json", storyboard)
            self.event("audio", "complete")
            if stop_after == "audio":
                return self.output / "timing.json"
            self.event("assets", "running", "查询勾选图标源并校验 SVG")
            asset_file = self.output / "storyboard_assets.json"
            if asset_file.exists():
                storyboard = json.loads(asset_file.read_text(encoding="utf-8"))
            else:
                for section in storyboard["sections"]:
                    section["assets"] = []
                    if self.config["assets"]["enabled"]:
                        for keyword in section.get("icon_keywords", [])[:self.config["assets"]["max_per_section"]]:
                            section["assets"].extend(self.assets.fetch(keyword))
                save_json(asset_file, storyboard)
                self.assets.save_attribution()
            self.event("assets", "complete", f"素材错误/缺失详见 assets.json；strict 模式可禁止降级")
            if stop_after == "assets":
                return asset_file
            self.event("code", "running", "生成配音时长驱动的 Manim 代码")
            codes = {}
            for section in storyboard["sections"]:
                codes[section["id"]] = self.cached_json(f"{section['id']}_code.json", self.prompt("code", code_prompt(section)), lambda value: validate_code(value, len(section["beats"])))
            self.event("code", "complete")
            if stop_after == "code":
                return self.output
            rendered_file = self.output / "rendered.json"
            self.event("render", "running", "本地渲染，失败自动回传代码模型修复")
            rendered = json.loads(rendered_file.read_text(encoding="utf-8")) if rendered_file.exists() else {}
            for section in storyboard["sections"]:
                section_id = section["id"]
                if section_id in rendered and Path(rendered[section_id]["video"]).is_file():
                    continue
                video, snippets, revision = self.render_with_repairs(section, codes[section_id], 0)
                save_json(self.output / f"{section_id}_code.json", snippets)
                codes[section_id] = snippets
                rendered[section_id] = {"video": str(video), "revision": revision}
                save_json(rendered_file, rendered)
            self.event("render", "complete")
            if stop_after == "render":
                return rendered_file
            self.event("review", "running" if self.vision else "skipped", "视觉抽帧自动评审" if self.vision else "视觉评审未启用")
            reviewed_file = self.output / "reviewed.json"
            if reviewed_file.exists():
                rendered = json.loads(reviewed_file.read_text(encoding="utf-8"))
            elif self.vision:
                for section in storyboard["sections"]:
                    section_id = section["id"]
                    video = Path(rendered[section_id]["video"])
                    snippets = codes[section_id]
                    revision = rendered[section_id]["revision"]
                    for round_number in range(self.config["vision"]["rounds"]):
                        frames = sample_frames(video, self.output / section_id / f"review_{round_number}", self.config["vision"]["frames"])
                        feedback = self.vision.json(self.prompt("review", review_prompt(section)), self.validate_feedback, images=frames)
                        save_json(self.output / f"{section_id}_review_{round_number}.json", feedback)
                        if not feedback["has_issues"]:
                            break
                        revised = self.text.json(self.prompt("code", code_prompt(section, snippets, json.dumps(feedback, ensure_ascii=False))), lambda value: validate_code(value, len(section["beats"])))
                        video, snippets, revision = self.render_with_repairs(section, revised, revision + 1)
                    rendered[section_id] = {"video": str(video), "revision": revision}
                    save_json(self.output / f"{section_id}_code.json", snippets)
                save_json(reviewed_file, rendered)
            else:
                save_json(reviewed_file, rendered)
            if self.vision:
                self.event("review", "complete", "抽样帧评审完成；请人工检查最终动态视频")
            if stop_after == "review":
                return reviewed_file
            self.event("compose", "running", "合并动画、配音和字幕")
            all_beats, videos, audios = [], [], []
            for section in storyboard["sections"]:
                videos.append(Path(rendered[section["id"]]["video"]))
                for index, beat in enumerate(section["beats"]):
                    padded = self.output / "audio" / f"{section['id']}_{index + 1:02}_padded.wav"
                    fit_audio(Path(beat["audio"]), padded, beat["duration"])
                    audios.append(padded)
                    all_beats.append(beat)
            concat(videos, self.output / "animation.mp4")
            concat(audios, self.output / "narration.wav", audio=True)
            duration = write_subtitles(all_beats, self.output / "subtitles.srt")
            save_json(self.output / "timeline.json", all_beats)
            final = self.output / "final.mp4"
            mux(self.output / "animation.mp4", self.output / "narration.wav", self.output / "subtitles.srt", final, duration)
            details = probe(final)
            if not {"video", "audio", "subtitle"}.issubset({stream["type"] for stream in details["streams"]}):
                raise RuntimeError("最终视频缺少视频、音频或字幕轨")
            if abs(details["duration"] - duration) > 0.2:
                raise RuntimeError("最终视频时长异常")
            self.manifest.update({"status": "complete", "media": details, "output": str(final)})
            self.event("compose", "complete")
            return final
        except Exception as failure:
            self.manifest["status"] = "failed"
            if self.active_stage:
                self.event(self.active_stage, "failed", str(failure)[:1000])
            raise
        finally:
            if self.manifest["status"] == "started":
                self.manifest["status"] = "ready"
            self.manifest["usage"] = {"text": self.text.usage, "vision": self.vision.usage if self.vision else {}}
            save_json(self.output / "manifest.json", self.manifest)

    @staticmethod
    def validate_feedback(value):
        if not isinstance(value.get("has_issues"), bool) or not isinstance(value.get("suggested_improvements"), list):
            raise ValueError("视觉评审 JSON 结构不合法")
        if not all(isinstance(item, str) for item in value["suggested_improvements"]):
            raise ValueError("评审意见必须是字符串数组")
