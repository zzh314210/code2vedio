import ast
import copy
import hashlib
import json
import math
import os
import re
import sys
import textwrap
from pathlib import Path, PurePosixPath, PureWindowsPath

from configuration import public_config, sanitize_error
from lesson_prompts import outline_prompt, storyboard_prompt, code_prompt, review_prompt
from materials import load_materials
from media import concat, fit_audio, prepend_audio_silence, mux, probe, run_command, sample_frames, write_subtitles
from model_gateway import ModelGateway, StructuredOutputError
from narration import Narrator
from planning_review import PlanningPending
from teaching_research import enabled_for, prepare_research, research_context, validate_step_coverage, validate_plan
from series_style import validate_style_snippet
from styles import StylePackage, load_style, snapshot_hash, style_video_config, style_stage_policy
from icon_assets import AssetManager
from project_extensions import read_extensions
from video_project import archive_resource, initialize_project, input_fingerprint, local_assets, read_templates, snapshot_materials


def save_json(filename, value):
    from execution import validate_output
    validate_output(filename.parent, filename)
    temporary = filename.with_suffix(filename.suffix + ".tmp")
    validate_output(filename.parent, temporary)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(filename)


class NarrationBudgetError(ValueError):
    pass


def nonempty(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} 必须是非空字符串且不超过 {maximum} 字")


def validate_video_constraints(video):
    for key, choices, default in (("layout", ("classic", "minimal", "canvas"), "classic"), ("theme", ("light", "dark"), "dark"), ("orientation", ("landscape", "portrait"), "landscape")):
        if video.get(key, default) not in choices:
            raise ValueError(f"Invalid video.{key}; expected one of {choices}")
    for key in ("reset_between_beats", "exit_fade", "style_lock", "fixed_beat_durations"):
        if key in video and not isinstance(video[key], bool):
            raise ValueError(f"video.{key} must be boolean")
    palette = video.get("style_palette", {})
    if not isinstance(palette, dict):
        raise ValueError("video.style_palette must be an object")
    for key, color in palette.items():
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError(f"video.style_palette.{key} must be a six-digit hex color")
    for key, default in (("narration_max_chars", 140), ("caption_max_chars", 42)):
        value = video.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4000:
            raise ValueError(f"video.{key} 必须是 1-4000 的整数")
    language = video.get("subtitle_language", "zho")
    if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{3}", language):
        raise ValueError("video.subtitle_language 必须是三字母字幕语言代码")


def validate_snippet(code, extensions=None, runtime=None):
    nonempty(code, "Manim code", 24000)
    tree = ast.parse(code)
    from scene_api import validate_calls
    validate_calls(tree, runtime)
    prohibited = (ast.Import, ast.ImportFrom, ast.While, ast.With, ast.AsyncWith, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Return, ast.Raise, ast.Try, ast.Global, ast.Nonlocal)
    denied_names = {"open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals", "vars", "input", "breakpoint", "__import__", "Tex", "MathTex", "SVGMobject", "ImageMobject"}
    allowed_methods = {"play", "wait", "add", "remove", "scene_text", "scene_paragraph", "sketch_line", "asset", "extension", "style_color", "sketch_shape", "ink_path"}
    # Catch invented constructors before spending minutes on a full render.
    # Only check direct class-like calls; local variables/method chains retain
    # normal Python semantics and the existing sandbox remains authoritative.
    from execution import manim_api_names
    api_names = manim_api_names()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'self'
                and node.func.attr == 'extension' and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'function_plot'):
            for keyword in node.keywords:
                if keyword.arg == 'label' and isinstance(keyword.value, ast.Constant):
                    if not isinstance(keyword.value.value, str) or len(keyword.value.value) > 24:
                        raise ValueError('函数图标题最多24字，较长解释请放入旁白。')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name[:1].isupper() and name not in api_names:
                raise ValueError(f"Manim 没有 {name}。请使用真实 API，例如 DashedVMobject(Circle(...))；不要编造类名。")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr == "extension":
            calls = [call for call in ast.walk(tree) if isinstance(call, ast.Call) and call.func is node]
            if not calls or not calls[0].args or not isinstance(calls[0].args[0], ast.Constant) or not isinstance(calls[0].args[0].value, str) or calls[0].args[0].value not in (extensions or {}):
                raise ValueError("扩展调用必须直接使用本项目注册的名称字面量")
        if isinstance(node, prohibited):
            raise ValueError(f"第{getattr(node, 'lineno', '?')}行含禁止的{type(node).__name__}；代码必须直接内联，不能包含import/while/with/类/函数/异常控制")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in denied_names):
            raise ValueError(f"不允许的代码标识符: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError("代码不能访问私有/反射属性")
            if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr not in allowed_methods:
                raise ValueError(f"不允许访问 self.{node.attr}")
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                raise ValueError("不能修改对象属性，请使用 Manim 方法")


def validate_code(value, count, extensions=None, video=None, runtime=None):
    if not isinstance(value, dict) or not isinstance(value.get("beats"), list) or len(value["beats"]) != count:
        raise ValueError(f"代码必须包含 {count} 个 beats")
    for index, beat in enumerate(value["beats"], 1):
        try:
            validate_snippet(beat["code"], extensions, runtime)
            validate_style_snippet(beat["code"], video)
        except (ValueError, SyntaxError) as error:
            raise ValueError(f"第{index}个分镜：{error}") from error


STAGES = ["outline", "storyboard", "criteria", "audio", "assets", "code", "render", "review", "compose", "acceptance"]


def review_summary(output, rendered, enabled):
    sections = {}
    for section_id, artifact in rendered.items():
        status = "unverified" if enabled else "disabled"
        files = sorted(Path(output).glob(f"{section_id}_review_*.json")) if enabled else []
        for filename in files:
            feedback = json.loads(filename.read_text(encoding="utf-8"))
            if feedback.get("reviewed_revision") == artifact["revision"]:
                status = "issues_found" if feedback["has_issues"] else "passed"
        sections[section_id] = {"revision": artifact["revision"], "status": status}
    return {"passed": bool(sections) and all(item["status"] == "passed" for item in sections.values()), "sections": sections}


def task_fingerprint(topic, config, materials):
    sources = [{key: value for key, value in source.items() if key != "path"} for source in materials["sources"]]
    payload = {"version": 2, "topic": topic, "config": config, "sources": sources, "context": materials["context"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def resume_vision_changed(topic, config, materials, existing):
    """Allow resource/output budget increases without re-buying valid output."""
    if task_fingerprint(topic, config, materials)==existing['fingerprint']:
        return False
    old=existing.get('config',{})
    limits={'memory','cpus','pids_limit'}
    current_execution=config.get('execution',{})
    old_execution=old.get('execution',{})
    if {k:v for k,v in current_execution.items() if k not in limits}!={k:v for k,v in old_execution.items() if k not in limits}:
        raise ValueError('渲染后端与缓存不一致，请创建新项目。')
    previous=json.loads(json.dumps(config))
    old_text = old.get('text', {})
    new_text = config.get('text', {})
    # Increasing the completion budget cannot invalidate previously validated
    # planning/audio. Every other text setting must still match the archive.
    if new_text.get('max_tokens', 0) >= old_text.get('max_tokens', 0):
        previous.setdefault('text', {}).pop('max_tokens', None)
        if 'max_tokens' in old_text:
            previous['text']['max_tokens'] = old_text['max_tokens']
    if 'execution' in old:previous['execution']=old_execution
    else:previous.pop('execution',None)
    previous['vision']=old.get('vision',{})
    if task_fingerprint(topic,previous,materials)!=existing['fingerprint']:
        raise ValueError('模型/素材/配置与缓存不一致，请使用新输出目录，避免复用过期分镜/配音')
    return config.get('vision',{})!=old.get('vision',{})


class VideoPipeline:
    def __init__(self, topic, config, output, materials=None, pages=None, resume=False, on_event=None, project=None, references=None, planning_gate=None):
        self.planning_gate = planning_gate
        self.teaching_research = None
        from execution import project_lock
        root = Path(project or output).resolve()
        root.mkdir(parents=True, exist_ok=True)
        with project_lock(root):
            self._initialize(topic, config, output, materials, pages, resume, on_event, project, references)

    def _initialize(self, topic, config, output, materials=None, pages=None, resume=False, on_event=None, project=None, references=None):
        self.topic = topic
        self.config = json.loads(json.dumps(config))
        style_id = self.config.get("style", "default")
        style_id = style_id.get("id", "default") if isinstance(style_id, dict) else style_id
        from execution import validate_output
        project_root = Path(project or output).resolve()
        snapshot_file = validate_output(project_root, project_root / "prompts/style.json")
        self.style_snapshot = None
        if resume and snapshot_file.is_file():
            snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
            if (not isinstance(snapshot, dict) or snapshot.get("id") != style_id
                    or not isinstance(snapshot.get("video"), dict)
                    or not isinstance(snapshot.get("policy"), str)
                    or not isinstance(snapshot.get("stages", {}), dict)
                    or any(not isinstance(value, str) for value in snapshot.get("stages", {}).values())):
                raise ValueError("Invalid project style snapshot or mismatched style id")
            self.style_snapshot = snapshot
            if snapshot.get("content_hash") and snapshot_hash(snapshot) != snapshot["content_hash"]:
                raise ValueError("Project style snapshot content hash mismatch")
            self.style = StylePackage(style_id, snapshot.get("title", style_id),
                                      snapshot.get("description", ""), snapshot["video"],
                                      snapshot_file.parent, snapshot["policy"], snapshot.get("version", "1.0.0"), snapshot.get("technical", {}), snapshot.get("sources", []))
        else:
            self.style = load_style(style_id)
        self.config = style_video_config(self.config, self.style)
        validate_video_constraints(self.config["video"])
        self.on_event = on_event or (lambda event: None)
        self.active_stage = None
        self.output = Path(output).resolve()
        project_root = Path(project or output).resolve()
        if not self.output.is_relative_to(project_root):
            raise ValueError("Output must be inside the current video project")
        self.output.mkdir(parents=True, exist_ok=True)
        self.project = initialize_project(project or self.output, topic, self.config)
        self.config["course"] = json.loads((self.project / "prompts/requirements.json").read_text(encoding="utf-8-sig"))
        self.config["task"] = self.config["course"]
        if not isinstance(self.config["course"], dict):
            raise ValueError("项目 requirements.json 必须是课程要求 JSON 对象")
        self.templates = read_templates(self.project)
        self.extensions = read_extensions(self.project / "code/runtime")
        material_paths = snapshot_materials(self.project, materials or [], resume)
        reference_paths = snapshot_materials(self.project, references or [], resume, "input/references")
        if not resume:
            for filename in material_paths + reference_paths:
                source = Path(filename)
                if source.suffix.lower() == ".svg":
                    data = source.read_bytes()
                    identifier = hashlib.sha256(data).hexdigest()[:12]
                    archive_resource(self.project, f"reference_{identifier}.svg", data)
        style_file = self.project / "prompts/style.json"
        if not resume:
            self.style_snapshot = self.style.snapshot()
            save_json(style_file, self.style_snapshot)
        inputs_hash = input_fingerprint(self.project)
        self.materials = load_materials(material_paths, topic, self.config["materials"], pages, reference_paths, self.output / "reference_transcripts")
        self.reference_images = [Path(item["path"]) for item in self.materials.get("visual_inputs", []) if item["type"] == "image"]
        for item in self.materials.get("visual_inputs", []):
            if item["type"] == "video":
                frames_directory = self.output / "reference_frames" / item["sha256"]
                self.reference_images.extend(sample_frames(Path(item["path"]), frames_directory, 3))
        self.request_directory = self.output / "requests"
        self.request_directory.mkdir(exist_ok=True)
        self.request_serial = max((int(file.name.split("-", 1)[0]) for file in self.request_directory.glob("*.txt") if file.name.split("-", 1)[0].isdigit()), default=0)
        self.text = ModelGateway(config["text"], on_request=self.record_request)
        self.vision = ModelGateway(config["vision"], "vision", on_request=self.record_request) if config["vision"]["enabled"] else None
        self.narrator = Narrator(config["tts"])
        self.assets = AssetManager(config["assets"], self.output)
        public = public_config(self.config)
        fingerprint = task_fingerprint(topic, public, self.materials)
        manifest = self.output / "manifest.json"
        vision_changed = False
        if manifest.exists():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if not resume:
                raise ValueError("输出目录已存在任务；请使用新目录或 --resume")
            if existing.get("inputs_fingerprint") not in (None, inputs_hash):
                raise ValueError("项目提示词、示例或绘图代码已修改，请创建新项目版本，不能复用旧缓存")
            vision_changed = resume_vision_changed(topic, public, self.materials, existing)
            self.relocate_caches(existing)
            if vision_changed:
                for stale_review in (self.output / "reviewed.json", *self.output.glob("*_review_*.json")):
                    stale_review.unlink(missing_ok=True)
        self.manifest = {"fingerprint": fingerprint, "inputs_fingerprint": inputs_hash, "project_directory": str(self.project), "topic": topic, "config": public, "status": "started", "stages": {}}
        if resume and manifest.exists():
            self.manifest["stages"] = existing.get("stages", {})
        if vision_changed:
            for stage in ("review", "compose"):
                self.manifest["stages"].pop(stage, None)
        self.harness = None
        self.acceptance = None
        if self.config.get('quality',{}).get('enabled'):
            from quality_harness import QualityHarness
            self.harness = QualityHarness(self)
            self.acceptance = ModelGateway(config.get('acceptance',config['text']), 'acceptance', on_request=self.record_request)
            for gateway in (self.text,self.vision,self.acceptance):
                if gateway:
                    gateway.budget=self.harness.budget
                    if getattr(gateway,'client',None):gateway.client.max_retries=0
            self.config['video']['fix_attempts']=self.harness.policy['render_revisions']
            if self.vision:self.config['vision']['rounds']=self.harness.policy['visual_revisions']
        self.manifest["output_directory"] = str(self.output)
        save_json(manifest, self.manifest)
        save_json(self.output / "materials.json", self.materials)
        if self.materials["omitted_chunks"]:
            print(f"素材超过上下文预算，已选取相关片段；省略 {self.materials['omitted_chunks']} 段，详见 materials.json")

    def relocate_caches(self, existing):
        old_root_text = existing.get("project_directory") or str(self.project)
        path_type = PureWindowsPath if PureWindowsPath(old_root_text).drive else PurePosixPath
        old_root = path_type(old_root_text)
        if not old_root.is_absolute():
            raise ValueError("Cached project root must be absolute")
        try:
            output_relative = self.output.relative_to(self.project)
        except ValueError as failure:
            raise ValueError("Resume output must be inside the video project") from failure
        old_output = path_type(existing.get("output_directory") or str(old_root / output_relative.as_posix()))
        if existing.get("output") and not existing.get("output_directory"):
            old_output = path_type(existing["output"]).parent
        old_output.relative_to(old_root)

        def relocate_path(value):
            if not isinstance(value, str) or not value:
                raise ValueError("Invalid cached media path")
            cached = path_type(value)
            if ".." in cached.parts:
                raise ValueError("Cached media path contains traversal")
            if cached.is_absolute():
                for previous, current in ((old_output, self.output), (old_root, self.project)):
                    try:
                        relative = cached.relative_to(previous)
                    except ValueError:
                        continue
                    target = current.joinpath(*relative.parts).resolve()
                    break
                else:
                    raise ValueError("Cached media path is outside the archived project")
            else:
                if cached.drive or cached.root:
                    raise ValueError("Invalid rooted cached media path")
                target = self.project.joinpath(*cached.parts).resolve()
            if not target.is_relative_to(self.project):
                raise ValueError("Cached media path escapes the video project")
            return str(target)

        def relocate(value):
            if isinstance(value, list):
                return [relocate(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, item in value.items():
                if key in ("audio", "video", "path") and isinstance(item, str):
                    result[key] = relocate_path(item)
                elif key == "images" and isinstance(item, list):
                    result[key] = [relocate_path(image) for image in item]
                else:
                    result[key] = relocate(item)
            return result

        updates = []
        invalid_render = False
        for filename in sorted(self.output.rglob("*.json")):
            relative = filename.relative_to(self.output)
            if len(relative.parts) > 1 and relative.parts[0] not in {
                    "audio", "assets", "requests", "reference_transcripts", "reference_frames"}:
                continue
            if filename == self.output / "manifest.json":
                continue
            if not filename.resolve().is_relative_to(self.output):
                raise ValueError("Cache file escapes the output directory")
            original = json.loads(filename.read_text(encoding="utf-8"))
            relocated = relocate(original)
            if filename.name in ("rendered.json", "reviewed.json"):
                relocated = {key: item for key, item in relocated.items() if Path(item["video"]).is_file()}
                invalid_render = invalid_render or len(relocated) != len(original)
            if original != relocated:
                updates.append((filename, relocated))
        for filename, relocated in updates:
            save_json(filename, relocated)
        if invalid_render:
            (self.output / "reviewed.json").unlink(missing_ok=True)

    def record_request(self, role, prompt, images):
        self.request_serial += 1
        name = f"{self.request_serial:04}-{self.active_stage or 'prepare'}-{role}"
        (self.request_directory / (name + ".txt")).write_text(sanitize_error(prompt, self.config), encoding="utf-8")
        settings = ({'text':self.text,'vision':self.vision,'acceptance':getattr(self,'acceptance',None)}[role]).settings
        snapshot = self.style_snapshot or self.style.snapshot()
        save_json(self.request_directory / (name + ".json"), {"role": role, "stage": self.active_stage, "model": settings["model"], "protocol": settings["protocol"], "max_tokens": settings.get("max_tokens"), "reasoning_policy":settings.get('effective_reasoning'), "style_id": snapshot["id"], "style_version": snapshot.get("version"), "style_hash": snapshot.get("content_hash"), "images": [str(file) for file in images]})

        return self.active_stage or "prepare"

    def cached_json(self, filename, prompt, validator):
        if getattr(self, 'logic_proof', None) and filename in ('outline.json', 'storyboard.json'):
            contract,unused=self.logic_modules()
            lesson_plan,validate_plan_handoff=contract.lesson_plan,contract.validate_plan_handoff
            outline, board = lesson_plan(self.logic_proof)
            result = outline if filename == 'outline.json' else board
            stage = 'outline' if filename == 'outline.json' else 'storyboard'
            file = self.output / filename
            if file.exists(): result = json.loads(file.read_text(encoding='utf8'))
            validate_plan_handoff(result, self.logic_proof, stage)
            validator(result)
            save_json(file, result)
            self.seal_handoff(filename, result, prompt)
            return result
        file = self.output / filename
        if file.exists():
            result = json.loads(file.read_text(encoding="utf-8"))
            validator(result)
            self.seal_handoff(filename, result, prompt)
            return result
        images = self.reference_images if filename in ("outline.json", "storyboard.json") else []
        try:
            result = self.text.json(prompt, validator, images=images)
        except StructuredOutputError as error:
            # A structurally sound storyboard can still be too verbose after
            # general retries. Repair only speech, preserving every visual,
            # fact constraint, section, and recall pause for full revalidation.
            if filename != "storyboard.json" or not isinstance(error.validation_error, NarrationBudgetError) or not isinstance(error.candidate, dict):
                raise
            candidate = copy.deepcopy(error.candidate)
            beats = [beat for section in candidate["sections"] for beat in section["beats"]]
            target = self.config["video"]["target_duration"]
            request = "你是短视频旁白编辑。只压缩每段narration，不重写分镜。删除重复与开场套话，保留事实、数字、结论、公式的适用条件和提问答案。复杂计算可以交给已有画面，但不能说反或漏掉必要条件。不要加快语速，也不要截断句子。"
            request += f"\n全片目标{target}秒，总旁白控制在约{int(target*2.7)}个中文字符以内。按原顺序返回恰好{len(beats)}个旁白，格式只需 {{\"narrations\":[\"第一段\",\"第二段\"]}}。"
            request += "\n原始分镜与必须保留的画面/问答：\n" + json.dumps(candidate, ensure_ascii=False)
            def validate_shortened(value):
                lines = value.get("narrations") if isinstance(value, dict) else None
                if not isinstance(lines, list) or len(lines) != len(beats):
                    raise ValueError("压缩旁白必须逐段对应，不能增删或重排段落")
                for beat, line in zip(beats, lines):
                    nonempty(line, "narration", self.config["video"].get("narration_max_chars", 140))
                    beat["narration"] = line
                validator(candidate)
            if getattr(self,"harness",None):self.harness.budget.take_revision("planning","structured-text-storyboard")
            self.text.json(request, validate_shortened, attempts=2, images=images)
            result = candidate
        save_json(file, result)
        self.seal_handoff(filename, result, prompt)
        return result

    def seal_handoff(self, filename, document, prompt=''):
        """Bind every generated artifact to its actual upstream prompt and body."""
        from logic_contract import digest
        file = self.output / 'handoff_receipts.json'
        receipts = json.loads(file.read_text()) if file.exists() else {}
        # Root relocation is an authorized operation already checked by the
        # project input fingerprint and safe-path relocation above. Absolute
        # audio/asset paths do not change the semantic prompt on a project copy.
        stable_prompt=prompt.replace(str(self.output),'<project-output>').replace(str(self.project),'<project>')
        receipt = {'document_sha256': digest(document), 'input_sha256': digest(stable_prompt),
                   'proof_hash': getattr(self, 'logic_proof', {}).get('proof_hash')}
        previous = receipts.get(filename)
        if previous and previous != receipt:
            raise ValueError(f'{filename} 的内容或上游依据已变化，禁止复用旧的下游缓存；请创建新版本。')
        receipts[filename] = receipt
        save_json(file, receipts)

    def logic_modules(self):
        if not hasattr(self,'_logic_modules_cache'):
            from logic_runtime import load_runtime
            self._logic_modules_cache=load_runtime(self.project)
        return self._logic_modules_cache

    def reseal_document(self, filename, document, reason):
        """Record a pipeline-authorized repair; arbitrary cache edits still fail."""
        from logic_contract import digest
        file = self.output / 'handoff_receipts.json'
        receipts = json.loads(file.read_text()) if file.exists() else {}
        if filename not in receipts: return
        previous = receipts[filename]
        receipts[filename] = {**previous, 'document_sha256': digest(document)}
        save_json(file, receipts)
        history = self.output / 'handoff_updates.jsonl'
        with history.open('a', encoding='utf8') as stream:
            stream.write(json.dumps({'artifact':filename,'reason':reason,'previous':previous,'current':receipts[filename]},ensure_ascii=False)+'\n')

    def prompt(self, stage, original):
        snapshot = getattr(self, "style_snapshot", None)
        policy = (snapshot.get("stages", {}).get(stage, self.style.policy)
                  if snapshot is not None else style_stage_policy(self.style, stage))
        original += "\n视频画面风格：\n" + policy
        technical = snapshot.get("technical", {}) if snapshot is not None else self.style.technical
        original += "\n固定公共技术技能：\n" + technical.get(stage, "")
        original += "\n运行时配置（必须遵守）：" + json.dumps(self.config["video"], ensure_ascii=False)
        original += "\n用户视频任务：" + self.topic
        course = self.config.get("task", self.config.get("course", {}))
        if stage == "storyboard":
            video = self.config["video"]
            original += "\n可设置 lead_in_seconds 为0到30秒的静默读题前置时间；配音和字幕自动延后。video.fixed_beat_durations=true 时 duration_seconds 为该段总时长（含读题），旁白必须在该段内说完。"
            if video.get("target_duration"):
                original += f"\n总时长目标 {video['target_duration']} 秒；中文旁白建议不超过 {int(video['target_duration'] * (2.8 if course.get('template_id') else 3.8))} 字，预留动画停顿。可以给每个beat添加正数duration_seconds作为视觉时间权重。"
            original += '\n回忆题请将提问与答案拆成两个beats；提问beat设置hold_after_seconds=2，旁白说完后会真正停顿两秒，再进入答案镜头。hold_after_seconds允许0至10秒，计入总时长。'
            original += f"\n本项目每个 beat 的字符上限：narration ≤{video.get('narration_max_chars', 140)}，caption ≤{video.get('caption_max_chars', 42)}。"
        if stage == "code":
            from scene_api import reference
            original += "\n" + reference(self.project / "code/runtime")
            descriptions = {name: entry.get("description", "") for name, entry in self.extensions.items()}
            original += "\n本项目允许的动画扩展（空对象表示无扩展；调用 self.extension(名称字面量, ...)，首个参数自动传入 scene）：" + json.dumps(descriptions, ensure_ascii=False)
        if stage == 'review':
            original += '\n字幕仅在对应subtitles的start/end期间显示；旁白结束后的停顿、回忆题留白和正常转场中字幕为空是预期行为。不要要求字幕常驻或把空字幕框本身当成错误。地图已经标有“地图定位示意”且地点关系正确时，不需要强制添加经纬度数字或比例尺。仍须核对地图位置、日期、文字重叠与内容遗漏。'
        if stage=='code' and getattr(self,'harness',None):
            original+='\n质量约束：严格保持已确认分镜与旁白；每个镜头必须以图形变化解释原理，不能只显示文字。保持角色、颜色、数值和因果关系一致。画布底部18%为字幕安全区，不在此处绘制内容或重复字幕。转场必须保留可理解的关系，不能出现长空白。验收失败后只修正明确问题，不简化标准。'
            if self.harness.contract:original+='\n冻结的验收标准：'+json.dumps(self.harness.contract['checks'],ensure_ascii=False)
        if stage in ("outline", "storyboard", "code") and getattr(self, "teaching_research", None):
            original += research_context(self.teaching_research)
        return original + f"\n项目语言：{course.get('language', '中文')}\n创作者课程要求（仍须符合事实和输出格式约束）：{course.get('instructions', '')}\n本阶段补充要求：{course.get('prompts', {}).get(stage, '')}"

    def event(self, stage, status, message=""):
        self.active_stage = stage
        for gateway in (self.text,self.vision,getattr(self,"acceptance",None)):
            if gateway:gateway.settings["usage_stage"]=stage
        event = {"stage": stage, "status": status, "message": sanitize_error(message, self.config)}
        with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.manifest["stages"][stage] = event
        save_json(self.output / "manifest.json", self.manifest)
        self.on_event(event)

    def validate_outline(self, outline):
        if getattr(self, 'logic_proof', None):
            validate_plan_handoff=self.logic_modules()[0].validate_plan_handoff
            validate_plan_handoff(outline, self.logic_proof, 'outline')
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
        valid_sources.update(item["name"] for item in self.materials.get("visual_inputs", []))
        if getattr(self, "teaching_research", None):
            valid_sources.update(source["id"] for source in self.teaching_research["sources"])
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
                raise ValueError("sources must use these exact strings (without square brackets): " + json.dumps(sorted(valid_sources), ensure_ascii=False))

        if getattr(self, "teaching_research", None):
            validate_step_coverage(outline, self.teaching_research["plan"], "outline")

    def validate_storyboard(self, storyboard, outline):
        if getattr(self, 'logic_proof', None):
            validate_plan_handoff=self.logic_modules()[0].validate_plan_handoff
            validate_plan_handoff(storyboard, self.logic_proof, 'storyboard')
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
                nonempty(beat["narration"], "narration", self.config["video"].get("narration_max_chars", 140))
                nonempty(beat["caption"], "caption", self.config["video"].get("caption_max_chars", 42))
                nonempty(beat["visual"], "visual")
                lead = beat.get("lead_in_seconds", 0)
                if isinstance(lead, bool) or not isinstance(lead, (int, float)) or not math.isfinite(lead) or not 0 <= lead <= 30:
                    raise ValueError("lead_in_seconds must be a finite number in [0,30]")
                hold = beat.get('hold_after_seconds', 0)
                if isinstance(hold, bool) or not isinstance(hold, (int, float)) or not math.isfinite(hold) or not 0 <= hold <= 10:
                    raise ValueError('hold_after_seconds must be a finite number in [0,10]')
                planned = beat.get("duration_seconds", 1)
                if isinstance(planned, bool) or not isinstance(planned, (int, float)) or not math.isfinite(planned) or not 0 < planned <= 120:
                    raise ValueError("duration_seconds must be a finite visual timing weight in (0,120]")
            keywords = section.get("icon_keywords", [])
            if not isinstance(keywords, list) or len(keywords) > 4 or any(not isinstance(term, str) or not re.fullmatch(r"[a-zA-Z0-9 -]{1,50}", term) for term in keywords):
                raise ValueError("icon_keywords 必须是最多 4 个简单英文关键词")

        target=self.config["video"].get("target_duration")
        task=self.config.get('task',{})
        if task.get('template_version',0)>=4 and task.get('template_id') in {'history_map','notes','math_visual','word_story'}:
            beats=[b for s in sections for b in s['beats']]
            questions=[i for i,b in enumerate(beats) if b.get('recall_role')=='question']
            if not questions or any(i+1>=len(beats) or beats[i+1].get('recall_role')!='answer' or beats[i].get('hold_after_seconds',0)<2 for i in questions):
                raise ValueError('请预留完整回忆问答：提问beat标recall_role=question且hold_after_seconds至少2秒；紧接一个recall_role=answer的答案beat。精简前面镜头，为最后问答留出两个beats，不得遗漏答案。')
            if task.get('template_version',0)>=5 and task.get('template_id')=='notes':
                for section in sections:
                    promised=re.search(r'([一二三123])道.{0,8}(?:小测|练习|题)',section['title'])
                    count=sum(beat.get('recall_role')=='question' for beat in section['beats'])
                    if promised and count!={'一':1,'二':2,'三':3,'1':1,'2':2,'3':3}[promised.group(1)]:
                        raise ValueError('小测数量必须与章节标题一致；每题需要独立提问、停顿和答案，不能标题写三题却只制作一题。')
        if target and self.config.get("task",{}).get("template_id"):
            # Count spoken content, not punctuation, spaces, or every letter in
            # an English word. The synthesized audio is still the final timing
            # authority; this early estimate only rejects clearly overfull text.
            def spoken_units(text):
                return sum(1 if not token.isascii() else max(1, len(token) / 3)
                           for token in re.findall(r"[\u4e00-\u9fff]|[A-Za-z]+|[0-9]", text))
            total=math.ceil(sum(spoken_units(b["narration"]) for s in sections for b in s["beats"]))
            limit=int(target*3.6)
            if total>limit:raise NarrationBudgetError(f"旁白约{total}个发音单位，{target}秒模板最多{limit}。请将每段旁白缩减到当前的{int(limit/total*85)}%以内，并保留必要事实，把非必要细节留给画面，不要增加解说速度。")
        if getattr(self, "teaching_research", None):
            validate_step_coverage(storyboard, self.teaching_research["plan"], "storyboard")

    def research_teaching(self):
        if self.config.get('task', {}).get('template_id') == 'truth_logic':
            self.prepare_logic()
            return
        if self.config.get('task', {}).get('reuse_verified_research'):
            self.teaching_research = json.loads((self.output / 'teaching_research/research.json').read_text(encoding='utf8'))
            for source in self.teaching_research['sources']:
                if hashlib.sha256(source['text'].encode()).hexdigest()!=source['sha256']:
                    raise ValueError('Archived teaching source hash mismatch')
            validate_plan(self.teaching_research['plan'], self.teaching_research['sources'])
            return
        settings = self.config.get("teaching_research", {})
        if enabled_for(self.topic, settings):
            self.teaching_research = prepare_research(self.topic, self.materials, settings, self.output / "teaching_research", self.text)

    def prepare_logic(self):
        contract,unused=self.logic_modules()
        extraction_prompt,solve=contract.extraction_prompt,contract.solve
        evidence = self.topic + '\n' + self.materials.get('context', '')
        path = self.output / 'logic_proof.json'
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf8'))
            proof = solve(previous['contract'], evidence)
            if previous != proof: raise ValueError('逻辑证明缓存或来源已变化，需创建新版本')
        else:
            def validate(value): solve(value, evidence)
            contract = self.text.json(extraction_prompt(evidence), validate)
            proof = solve(contract, evidence)
            # A second, separately prompted semantic check catches a wrong
            # translation before the mathematically correct solver trusts it.
            audit_prompt = '你是题干形式化审计员。逐句独立核对原话与命题编码，重点检查我/不是我/只有一人、其他人的范围。不能因为计算答案正确就批准错误翻译。仅输出JSON {"equivalent":true或false,"issues":["具体差异"]}。\n原文：'+evidence+'\n形式化与完整真值表：'+json.dumps(proof,ensure_ascii=False)
            def valid_audit(v):
                if v.get('equivalent') is not True or v.get('issues') != []: raise ValueError('题干形式化未通过独立语义核对：'+str(v.get('issues')))
            audit = self.text.json(audit_prompt, valid_audit, attempts=2)
            save_json(self.output/'logic_semantic_audit.json', {'proof_hash':proof['proof_hash'],**audit})
            save_json(path, proof)
        audit=json.loads((self.output/'logic_semantic_audit.json').read_text(encoding='utf8'))
        if audit.get('proof_hash')!=proof['proof_hash'] or audit.get('equivalent') is not True or audit.get('issues')!=[]:
            raise ValueError('题干缺少与当前证明对应的独立语义审核，禁止跳过核对。')
        self.logic_proof = proof
        self.seal_handoff('logic_proof.json', proof, evidence)

    def planning_checkpoint(self, stage, document):
        if getattr(self, "planning_gate", None):
            self.planning_gate(stage, document)

    def prepare(self):
        print("[1/6] 根据视频需求和参考素材生成大纲")
        self.research_teaching()
        outline = self.cached_json("outline.json", self.prompt("outline", outline_prompt(self.topic, self.materials, self.config["video"], self.templates)), self.validate_outline)
        self.planning_checkpoint("outline", outline)
        print("[2/6] 生成逐句旁白和动画分镜")
        storyboard = self.cached_json("storyboard.json", self.prompt("storyboard", storyboard_prompt(outline, self.materials, self.config["video"], self.templates)), lambda value: self.validate_storyboard(value, outline))
        self.planning_checkpoint("storyboard", storyboard)
        for warning in outline["warnings"]:
            print(f"内容核验提示: {warning}")
        return outline, storyboard

    def prepare_audio(self, section):
        fps = self.config["video"]["fps"]
        for index, beat in enumerate(section["beats"]):
            audio = self.output / "audio" / f"{section['id']}_{index + 1:02}.wav"
            metadata = audio.with_suffix(".json")
            lead = float(beat.get("lead_in_seconds", 0))
            audio_fingerprint = hashlib.sha256(json.dumps({"text": beat["narration"], "tts": public_config(self.config["tts"]), "subtitle_version": 3, "lead_in_seconds": lead}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            info = json.loads(metadata.read_text(encoding="utf-8")) if audio.is_file() and metadata.is_file() else {}
            if info.get("fingerprint") != audio_fingerprint:
                info = self.narrator.synthesize(beat["narration"], audio)
                if lead:
                    padded = audio.with_suffix(".lead.wav")
                    prepend_audio_silence(audio, padded, lead)
                    padded.replace(audio)
                    info["subtitles"] = [{**cue, "start": cue["start"] + lead, "end": cue["end"] + lead} for cue in info.get("subtitles", [])]
                info["lead_in_seconds"] = lead
                info["fingerprint"] = audio_fingerprint
                save_json(metadata, info)
            info["duration"] = probe(audio)["duration"]
            save_json(metadata, info)
            beat["duration"] = math.ceil((info["duration"] + self.config["video"]["pause_seconds"] + float(beat.get('hold_after_seconds', 0))) * fps) / fps
            if self.config["video"].get("fixed_beat_durations"):
                beat["duration"] = max(beat["duration"], float(beat.get("duration_seconds", beat["duration"])))
            beat["audio"] = str(audio)
            beat["subtitles"] = info.get("subtitles", [])
        return section

    def assemble_code(self, section, snippets):
        self.validate_snippets(snippets, len(section["beats"]))
        definitions = "from manim import *\nimport numpy as np\nimport math\nfrom scene_runtime import NarratedScene\n\n"
        style = {key: self.config["video"].get(key) for key in ("theme", "orientation", "brand", "style_palette", "layout", "reset_between_beats", "exit_fade", "template_id", "style_lock", "subtitle_mode")}
        background = self.config["video"].get("style_palette", {}).get("background", "#F7FAF7" if style["theme"] == "light" else "#0b1020")
        definitions += f"config.background_color = {background!r}\n"
        if style.get("style_lock"):
            definitions += "from series_style import apply_style_defaults\n"
            definitions += f"apply_style_defaults({style!r}, {self.config['video']['font']!r})\n"
        if style["orientation"] == "portrait":
            definitions += "config.frame_width = 8\nconfig.frame_height = 14.2222222222\n"
        definitions += "\nclass LessonScene(NarratedScene):\n"
        definitions += f"    lesson_style = {style!r}\n"
        definitions += f"    lesson_title = {section['title']!r}\n    lesson_font = {self.config['video']['font']!r}\n"
        definitions += f"    lesson_beats = {section['beats']!r}\n\n    def construct(self):\n"
        asset_paths = {item["key"]: item["path"] for item in section.get("assets", [])}
        credits = " | ".join(sorted({item["credit"] for item in section.get("assets", [])}))
        if self.config.get('task',{}).get('template_id')=='word_story':
            credits=' | '.join(filter(None,[credits,'Noto Emoji / Google / Apache 2.0']))
        definitions = definitions.replace("\n\n    def construct(self):", f"\n    lesson_assets = {asset_paths!r}\n    lesson_credits = {credits!r}\n\n    def construct(self):")
        for index, beat in enumerate(snippets["beats"]):
            definitions += f"        self.begin_beat({index})\n"
            definitions += textwrap.indent(beat["code"].strip(), "        ") + "\n"
            definitions += "        self.end_beat()\n"
        ast.parse(definitions)
        return definitions

    def render(self, section, snippets, revision):
        if getattr(self, 'logic_proof', None):
            render_logic=self.logic_modules()[1].render_logic
            from execution import validate_output
            if snippets.get('proof_hash') != self.logic_proof['proof_hash']: raise ValueError('代码阶段的证明版本不一致')
            destination = validate_output(self.project,self.output / section['id'] / f'revision_{revision}' / 'lesson.mp4')
            return render_logic(section, self.logic_proof, destination, self.config['video'],
                lambda done,total:self.event('render','running',f'可验证图解渲染 {done}/{total}'))
        from execution import validate_output
        directory = validate_output(self.project, self.output / section["id"] / f"revision_{revision}")
        directory.mkdir(parents=True, exist_ok=True)
        script = validate_output(self.project, directory / "scene.py")
        script.write_text(self.assemble_code(section, snippets), encoding="utf-8")
        source_directory = validate_output(self.project, self.project / "code/manim")
        source_directory.mkdir(parents=True, exist_ok=True)
        validate_output(self.project, source_directory / f"{section['id']}_revision_{revision}.py").write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
        quality = {"low": "-ql", "medium": "-qm", "high": "-qh"}[self.config["video"]["quality"]]
        arguments = [sys.executable, "-m", "manim", quality, "--renderer", "cairo", "--fps", str(self.config["video"]["fps"]), "--disable_caching", "--media_dir", str(directory / "media"), "--output_file", "lesson", str(script), "LessonScene"]
        if self.config["video"].get("orientation") == "portrait":
            arguments[3:3] = ["--resolution", "1080,1920" if self.config["video"]["quality"] == "high" else "540,960"]
        try:
            from execution import render_command
            output = render_command(arguments, self.project, directory, self.config.get("execution", {}), self.config["video"]["render_timeout"])
            validate_output(self.project, directory / "render.log").write_text(output, encoding="utf-8")
        except RuntimeError as failure:
            validate_output(self.project, directory / "render.log").write_text(str(failure), encoding="utf-8")
            raise
        matches = list((directory / "media").rglob("lesson.mp4"))
        if len(matches) != 1:
            raise RuntimeError("Manim 未生成唯一 lesson.mp4")
        video = matches[0]
        expected = sum(beat["duration"] for beat in section["beats"])
        if abs(probe(video)["duration"] - expected) > max(0.12, 2 / self.config["video"]["fps"]):
            raise RuntimeError("动画时间轴与旁白时长不一致，需要修复代码")
        return video

    def validate_snippets(self, value, count):
        runtime = self.project / "code/runtime" if getattr(self, 'project', None) else None
        validate_code(value, count, self.extensions, self.config['video'], runtime)
        owned={'history_map':{'map_story'},'word_story':{'story_scene','vocabulary_card'},'product':{'media_shot'},'documentary':{'media_shot'},'notes':{'knowledge_map','function_plot'},'math_visual':{'function_plot'}}.get(self.config.get('task',{}).get('template_id'),set())
        if self.config.get('task',{}).get('template_id'):owned=owned|{'review_cards','recall_card','function_plot','formula_steps','lunar_phases'}
        if not owned:return
        for beat in value['beats']:
            calls=[node for node in ast.walk(ast.parse(beat['code'])) if isinstance(node,ast.Call)]
            def component(node):
                if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='self' and node.func.attr=='extension' and node.args and isinstance(node.args[0],ast.Constant) and node.args[0].value in owned:
                    return node.args[0].value
                return None
            chosen=[node for node in calls if component(node)]
            if not chosen:continue
            if len(chosen)>1:raise ValueError('同一分镜只能调用一次完整画布组件，避免主体与文字重叠。请把多个镜头拆成不同beats。')
            for node in calls:
                if component(node):continue
                if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='self' and node.func.attr=='wait':continue
                raise ValueError(f"{component(chosen[0])}组件已负责完整画布。只调用该组件（通过参数传入日期/事件/角色/词义），可加self.wait；不要额外画图、加字或移动组件。其他讲解镜头可单独不用该组件。")

    def render_with_repairs(self, section, snippets, start_revision):
        from execution import RenderInfrastructureError
        state_file=self.output / f"{section['id']}_repair_{start_revision}.json"
        seed=hashlib.sha256(json.dumps({'section':section,'snippets':snippets},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        first_attempt=0
        if state_file.exists():
            state=json.loads(state_file.read_text(encoding='utf8'))
            candidate=state.get('attempt')
            if state.get('seed')==seed and isinstance(candidate,int) and 0<=candidate<=self.config['video']['fix_attempts']:
                if not getattr(self,'logic_proof',None):self.validate_snippets(state['snippets'],len(section['beats']))
                snippets=state['snippets'];first_attempt=candidate
        for attempt in range(first_attempt,self.config["video"]["fix_attempts"] + 1):
            save_json(state_file,{'seed':seed,'attempt':attempt,'snippets':snippets})
            revision = start_revision + attempt
            save_json(self.output / f"{section['id']}_code_{revision}.json", snippets)
            try:
                return self.render(section, snippets, revision), snippets, revision
            except RenderInfrastructureError:
                raise
            except RuntimeError as failure:
                if attempt == self.config["video"]["fix_attempts"]:
                    detail = str(failure).strip()
                    errors = re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception): .+)$", detail)
                    reason = (errors[-1] if errors else detail.splitlines()[-1] if detail else "渲染器未返回错误详情")[:300]
                    title = section.get('title', section['id'])[:60]
                    raise RuntimeError(f"“{title}”动画制作失败，已自动修复 {attempt} 次。具体原因：{reason}") from failure
                if getattr(self,"harness",None):self.harness.budget.take_revision("render",section["id"])
                print(f"修复 {section['id']}，第 {attempt + 1} 次")
                snippets = self.text.json(self.prompt("code", code_prompt(section, snippets, str(failure)[-8000:], self.templates, self.config["video"])), lambda value: self.validate_snippets(value, len(section["beats"])))

    def assess_visual(self,section,frames,timestamps):
        """Corroborate a rejection before rewriting a film from sampled stills.

        Keep both opinions. A second check must judge the actual images and
        timings, including genuine errors, not automatically prefer acceptance.
        """
        prompt=self.prompt('review',review_prompt(section,self.templates,frame_timestamps=timestamps))
        first=self.vision.json(prompt,self.validate_feedback,images=frames)
        if not first['has_issues']:return first
        confirmation=self.vision.json(prompt+'\n下面是一份待核实的初审，可能正确也可能误读。请逐项对照附图与时间核实，而非照抄。真实问题必须保留；正常动画中间态、已经显示的文字以及没有证据的推测不能作为阻断理由。输出同一JSON结构，另可用polish_notes列出可选优化。\n待核实初审：'+json.dumps(first,ensure_ascii=False),self.validate_feedback,images=frames)
        confirmation['initial_assessment']=first
        return confirmation

    def run(self, plan_only=False, stop_after="compose"):
        from execution import project_lock
        with project_lock(self.project):
            return self._run(plan_only, stop_after)

    def _run(self, plan_only=False, stop_after="compose"):
        from quality_harness import QualityRejected
        while True:
            try:
                return self._run_once(plan_only,stop_after)
            except QualityRejected as failure:
                if not getattr(self,'harness',None) or self.active_stage!='acceptance':raise
                # Only the affected render/code can change. Approved narration,
                # outline, storyboard, proof and frozen criteria are immutable.
                try:
                    self.harness.budget.take_revision('final')
                    self.repair_quality_failure(failure.report)
                except Exception as stopped:
                    self.manifest['status']='failed'
                    self.event('acceptance','failed',str(stopped)[:1000])
                    save_json(self.output/'manifest.json',self.manifest)
                    raise

    def repair_quality_failure(self, report):
        failures=[x for x in report['checks'] if x.get('status')!='pass']
        if any(x.get('id')=='silence' for x in failures):
            raise ValueError('配音存在超过3.5秒的非规划静音，已保留报告并停止；需要检查配音服务，不会自动删改已确认旁白。')
        if failures and all(x.get('id') in ('duration','streams','decode','subtitles') for x in failures):
            self.event('compose','running','媒体完整性未通过，保留已验收镜头并重新合成')
            (self.output/'candidate.mp4').unlink(missing_ok=True)
            self.manifest['status']='started'
            return
        board=json.loads((self.output/'storyboard_assets.json').read_text())
        timing=json.loads((self.output/'timing.json').read_text())
        targets={x.get('section_id') for x in failures if x.get('section_id')}
        for failure in failures:targets.update(failure.get('section_ids',[]))
        if not targets:targets={s['id'] for s in board['sections']}
        rendered_file=self.output/'rendered.json'
        rendered=json.loads(rendered_file.read_text()) if rendered_file.exists() else {}
        for section in board['sections']:
            if section['id'] not in targets:continue
            measured=next(s for s in timing['sections'] if s['id']==section['id'])
            section={**section,'beats':measured['beats']}
            previous=json.loads((self.output/f"{section['id']}_code.json").read_text())
            self.event('code','running','按冻结验收标准修正未通过的镜头')
            if getattr(self,'logic_proof',None):raise ValueError('确定性推理图解未通过验收，需要修复图解模板；不会让模型改写已验证证明。')
            feedback=json.dumps({'frozen_contract':self.harness.contract,'failures':failures},ensure_ascii=False)
            revised=self.text.json(self.prompt('code',code_prompt(section,previous,feedback,self.templates,self.config['video'])),lambda v:self.validate_snippets(v,len(section['beats'])))
            save_json(self.output/f"{section['id']}_code.json",revised)
            self.reseal_document(f"{section['id']}_code.json",revised,'final acceptance repair')
            rendered.pop(section['id'],None)
        save_json(rendered_file,rendered)
        for name in ('reviewed.json','review_status.json'):(self.output/name).unlink(missing_ok=True)
        self.manifest['status']='started'

    def _run_once(self, plan_only=False, stop_after="compose"):
        try:
            if plan_only:
                stop_after = "storyboard"
            if stop_after not in STAGES:
                raise ValueError("无效流水线阶段")
            self.event("outline", "running", "根据视频需求和参考素材生成大纲")
            self.research_teaching()
            outline = self.cached_json("outline.json", self.prompt("outline", outline_prompt(self.topic, self.materials, self.config["video"], self.templates)), self.validate_outline)
            self.event("outline", "complete")
            self.planning_checkpoint("outline", outline)
            for warning in outline["warnings"]:
                print(f"内容核验提示: {warning}")
            if stop_after == "outline":
                return self.output / "outline.json"
            self.event("storyboard", "running", "生成逐句旁白和动画分镜")
            storyboard = self.cached_json("storyboard.json", self.prompt("storyboard", storyboard_prompt(outline, self.materials, self.config["video"], self.templates)), lambda value: self.validate_storyboard(value, outline))
            self.event("storyboard", "complete")
            self.planning_checkpoint("storyboard", storyboard)
            if stop_after == "storyboard":
                return self.output / "storyboard.json"
            if getattr(self,'harness',None):self.harness.ensure_contract(outline,storyboard)
            self.event("audio", "running", "合成旁白并测量真实时长")
            target = self.config["video"].get("target_duration")
            if target is not None and (isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or target <= 0):
                raise ValueError("video.target_duration must be positive and finite")
            for audio_round in range(3):
                for section in storyboard["sections"]:
                    section = self.prepare_audio(section)
                    save_json(self.output / f"{section['id']}_timing.json", section)
                spoken = sum(beat["duration"] for section in storyboard["sections"] for beat in section["beats"])
                if target is None or spoken <= target + 1 / self.config["video"]["fps"]:
                    break
                if getattr(self,'harness',None):
                    message=f'完整旁白需 {spoken:.1f} 秒，超出目标 {target} 秒；未截断配音，也未改写已确认的内容。请精简分镜旁白后重新确认，或新建更长的视频。'
                    if getattr(self,'planning_gate',None):
                        from planning_review import PlanningReview
                        review=PlanningReview(self.project);review.state['auto_approve']=False
                        review.state['pending_stage']='storyboard';review.state['stages'].setdefault('storyboard',{}).pop('approved_version',None);review.persist()
                        raise PlanningPending('storyboard',message)
                    raise ValueError(message)
                if audio_round == 2:
                    raise ValueError("Narration still exceeds target after two automatic revisions; no speech was truncated")
                if getattr(self,'logic_proof',None):
                    raise ValueError('完整推理配音超出目标时长，请增加时长；不会让模型删减已验证步骤或截断语音。')
                self.event("audio", "running", "正在自动精简旁白，以适应目标时长")
                correction = f"\n上一版真实配音加停顿为 {spoken:.2f} 秒，目标 {target} 秒。必须保留事实与推理，缩短旁白到原字符数的 {target / spoken * .85:.0%}。不要改变章节ID。返回完整分镜JSON。"
                storyboard = self.text.json(self.prompt("storyboard", storyboard_prompt(outline, self.materials, self.config["video"], self.templates)) + correction,
                    lambda value: self.validate_storyboard(value, outline))
                save_json(self.output / "storyboard.json", storyboard)
                self.reseal_document('storyboard.json',storyboard,'measured narration budget repair')
                self.planning_checkpoint("storyboard", storyboard)
            if target is not None:
                if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or target <= 0:
                    raise ValueError("video.target_duration must be positive and finite")
                beats = [beat for section in storyboard["sections"] for beat in section["beats"]]
                actual = sum(beat["duration"] for beat in beats)
                if actual > target + 1 / self.config["video"]["fps"]:
                    raise ValueError("Real narration exceeds target duration; shorten narration or change TTS speed, never truncate speech")
                # Spread spare time across the planned visual beats, rather than freezing the final frame.
                slack = 0 if getattr(self,'harness',None) else max(0, target - actual)
                weights = [max(0.1, float(beat.get("duration_seconds", 1))) for beat in beats]
                for beat, weight in zip(beats, weights):
                    beat["duration"] += math.floor(slack * weight / sum(weights) * self.config["video"]["fps"]) / self.config["video"]["fps"]
                if not getattr(self,'harness',None):beats[-1]["duration"] += max(0, target - sum(beat["duration"] for beat in beats))
                for section in storyboard["sections"]:
                    save_json(self.output / f"{section['id']}_timing.json", section)
            save_json(self.output / "timing.json", storyboard)
            if getattr(self,'harness',None):self.harness.timeline_check(storyboard)
            self.event("audio", "complete")
            if stop_after == "audio":
                return self.output / "timing.json"
            self.event("assets", "running", "准备已验证的人物与命题图解" if getattr(self,"logic_proof",None) else "查询勾选图标源并校验 SVG")
            asset_file = self.output / "storyboard_assets.json"
            if asset_file.exists():
                storyboard = json.loads(asset_file.read_text(encoding="utf-8"))
            else:
                owned_assets = local_assets(self.project)
                for index, item in enumerate(self.materials.get("visual_inputs", [])):
                    if item["type"] == "image":
                        owned_assets.append({"key": "reference_image_" + str(index), "path": item["path"], "credit": "User material: " + item["name"], "license": "Verify user material rights before publishing", "source": "local"})
                self.assets.records.extend(owned_assets)
                for section in storyboard["sections"]:
                    section["assets"] = owned_assets[:self.config["assets"]["max_per_section"]]
                    if self.config["assets"]["enabled"]:
                        for keyword in section.get("icon_keywords", [])[:self.config["assets"]["max_per_section"]]:
                            section["assets"].extend(self.assets.fetch(keyword))
                save_json(asset_file, storyboard)
                self.assets.save_attribution()
            self.event("assets", "complete", f"素材错误/缺失详见 assets.json；strict 模式可禁止降级")
            if stop_after == "assets":
                return asset_file
            self.event("code", "running", "将证明编译为同步图解" if getattr(self,"logic_proof",None) else "生成配音时长驱动的 Manim 代码")
            # Detect local validation failures before paying for generated code.
            from execution import manim_api_names
            if not getattr(self,'logic_proof',None):manim_api_names()
            codes = {}
            for section in storyboard["sections"]:
                if getattr(self, 'logic_proof', None):
                    code = {'engine':'logic_diagram','proof_hash':self.logic_proof['proof_hash'],'beats':[{'scene_id':b['scene_id']} for b in section['beats']]}
                    self.seal_handoff(f"{section['id']}_code.json",code,json.dumps(section,ensure_ascii=False,sort_keys=True))
                    save_json(self.output/f"{section['id']}_code.json",code)
                    codes[section['id']] = code
                else:
                    codes[section["id"]] = self.cached_json(f"{section['id']}_code.json", self.prompt("code", code_prompt(section, templates=self.templates, settings=self.config["video"])), lambda value: self.validate_snippets(value, len(section["beats"])))
            self.event("code", "complete")
            if stop_after == "code":
                return self.output
            rendered_file = self.output / "rendered.json"
            self.event("render", "running", "绘制人物、关系与检验过程" if getattr(self,"logic_proof",None) else "本地渲染，失败自动回传代码模型修复")
            rendered = json.loads(rendered_file.read_text(encoding="utf-8")) if rendered_file.exists() else {}
            if getattr(self,'logic_proof',None):
                receipt_matches=self.logic_modules()[1].receipt_matches
                for section in storyboard['sections']:
                    old=rendered.get(section['id'])
                    if old and not receipt_matches(Path(old['video']),section,self.logic_proof):
                        rendered.pop(section['id'])
                        (self.output/'reviewed.json').unlink(missing_ok=True)
                        for old_review in self.output.glob('*_review_*.json'):old_review.unlink(missing_ok=True)
            for section in storyboard["sections"]:
                section_id = section["id"]
                if section_id in rendered and Path(rendered[section_id]["video"]).is_file():
                    continue
                video, snippets, revision = self.render_with_repairs(section, codes[section_id], 0)
                save_json(self.output / f"{section_id}_code.json", snippets)
                self.reseal_document(f'{section_id}_code.json',snippets,'render repair result')
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
                    for round_number in range(self.config["vision"]["rounds"] + 1):
                        from media import sample_beat_frames
                        if getattr(self,'harness',None):
                            report=self.harness.review_video(video,{'sections':[section]},'section_'+section_id)
                            feedback={'has_issues':not report['passed'],'suggested_improvements':[x for x in report['checks'] if x['status']!='pass'],'quality_report':report}
                        else:
                            frames = sample_beat_frames(video, self.output / section_id / f"review_{round_number}", section["beats"], self.config["vision"]["frames"])
                            timestamps = json.loads((frames[0].parent / 'timestamps.json').read_text(encoding='utf8'))
                            feedback = self.assess_visual(section,frames,timestamps)
                        feedback["reviewed_revision"] = revision
                        save_json(self.output / f"{section_id}_review_{round_number}.json", feedback)
                        if not feedback["has_issues"] or round_number == self.config["vision"]["rounds"]:
                            break
                        if getattr(self, 'logic_proof', None):
                            raise ValueError('可验证图解视觉审核发现问题，成片暂不发布：'+json.dumps(feedback['suggested_improvements'],ensure_ascii=False))
                        if getattr(self,'harness',None):self.harness.budget.take_revision("visual",section_id)
                        revised = self.text.json(self.prompt("code", code_prompt(section, snippets, json.dumps(feedback, ensure_ascii=False), self.templates, self.config["video"])), lambda value: self.validate_snippets(value, len(section["beats"])))
                        video, snippets, revision = self.render_with_repairs(section, revised, revision + 1)
                    rendered[section_id] = {"video": str(video), "revision": revision}
                    save_json(self.output / f"{section_id}_code.json", snippets)
                    self.reseal_document(f'{section_id}_code.json',snippets,'visual repair result')
                save_json(reviewed_file, rendered)
            else:
                save_json(reviewed_file, rendered)
            if self.vision:
                summary = review_summary(self.output, rendered, True)
                save_json(self.output / "review_status.json", summary)
                self.manifest["visual_review"] = summary
                self.event("review", "complete" if summary["passed"] else "unverified", "章节画面审核通过，继续验收完整成片" if summary["passed"] else "章节尚未通过或修复后未复核，成片暂不交付")
            if stop_after == "review":
                return reviewed_file
            if self.vision and self.config["vision"].get("require_pass") and not summary["passed"]:
                if getattr(self,'harness',None):
                    issues=[]
                    for checked_section in storyboard['sections']:
                        checked=self.harness.review_video(Path(rendered[checked_section['id']]['video']),{'sections':[checked_section]},'section_'+checked_section['id'])
                        issues.extend(checked['checks'])
                    report={'passed':False,'checks':issues,'scope':'sections'}
                    save_json(self.harness.directory/'failure.json',report)
                    from quality_harness import QualityRejected
                    raise QualityRejected(report)
                raise ValueError("Visual review still found issues; final video withheld. See review_status.json and review feedback.")
            part_receipts=[]
            if getattr(self,'harness',None):
                from quality_harness import QualityRejected
                for section in storyboard['sections']:
                    part=self.harness.review_video(Path(rendered[section['id']]['video']),{'sections':[section]},'section_'+section['id'])
                    if not part['passed']:
                        save_json(self.harness.directory/'failure.json',part)
                        raise QualityRejected(part)
                    part_receipts.append({'section_id':section['id'],'passed':True,'media_sha256':part['media_sha256'],'report_hash':part['report_hash']})
            self.event("compose", "running", "合并动画、配音和字幕")
            all_beats, videos, audios = [], [], []
            for section in storyboard["sections"]:
                videos.append(Path(rendered[section["id"]]["video"]))
                for index, beat in enumerate(section["beats"]):
                    padded = self.output / "audio" / f"{section['id']}_{index + 1:02}_padded.wav"
                    if probe(Path(beat["audio"]))["duration"] > beat["duration"] + 0.001:
                        raise ValueError("Audio exceeds allocated beat duration; refusing to truncate speech")
                    fit_audio(Path(beat["audio"]), padded, beat["duration"])
                    audios.append(padded)
                    all_beats.append(beat)
            concat(videos, self.output / "animation.mp4")
            concat(audios, self.output / "narration.wav", audio=True)
            duration = write_subtitles(all_beats, self.output / "subtitles.srt")
            save_json(self.output / "timeline.json", all_beats)
            final = self.output / ("candidate.mp4" if getattr(self,'harness',None) else "final.mp4")
            video, audio = self.output / "animation.mp4", self.output / "narration.wav"
            montage_settings = self.config.get("montage", {})
            if montage_settings:
                from montage import compose_media
                video, audio = compose_media(video, audio, self.output / "montage.mp4",
                                            self.output / "mixed.wav", duration,
                                            montage_settings, self.materials["sources"])
            from background_music import compose_background_music
            music = self.config.get('background_music', {})
            if music.get('enabled'):
                self.event('compose', 'running', '正在合成背景音乐，自动循环并降低旁白期间的音量')
                audio = compose_background_music(self.project, audio, self.output, duration, music)
                self.manifest['background_music'] = music
            mux(video, audio, self.output / "subtitles.srt", final, duration, self.config["video"].get("subtitle_language", "zho"), subtitle_mode=self.config["video"].get("subtitle_mode","soft"))
            details = probe(final)
            required_streams={"video","audio"}|({"subtitle"} if self.config["video"].get("subtitle_mode")!="off" else set())
            if not getattr(self,"harness",None) and not required_streams.issubset({stream["type"] for stream in details["streams"]}):
                raise RuntimeError("最终视频缺少视频、音频或字幕轨")
            if not getattr(self,"harness",None) and abs(details["duration"] - duration) > 0.2:
                raise RuntimeError("最终视频时长异常")
            if getattr(self,'logic_proof',None):
                from logic_acceptance import final_receipt
                receipts=[json.loads(Path(rendered[s['id']]['video']).with_suffix('.receipt.json').read_text()) for s in storyboard['sections']]
                save_json(self.output/'logic_final_acceptance.json',final_receipt(self.logic_proof,storyboard,final,details,self.logic_modules()[0],receipts))
            if getattr(self,'harness',None):
                from quality_harness import QualityRejected
                self.event('acceptance','running','按冻结标准验收完整成片、全部字幕、画面连续性和静音')
                host=self.harness.final_checks(final,storyboard,self.output/'narration.wav')
                visual=self.harness.review_video(final,storyboard,'final') if host['passed'] else {'passed':False,'checks':[],'frame_count':0}
                report=self.harness.report(host,visual,part_receipts)
                self.manifest['quality_acceptance']={k:v for k,v in report.items() if k!='checks'}
                if not report['passed']:raise QualityRejected(report)
                destination=self.output/'final.mp4';final.replace(destination);final=destination
                self.event('acceptance','complete','全部质量门禁通过，可以领取成片')
            self.manifest.update({"status": "complete", "media": details, "output": str(final)})
            self.event("compose", "complete")
            return final
        except PlanningPending as pending:
            self.manifest["status"] = "awaiting_review"
            self.event(pending.stage, "awaiting_review", str(pending))
            raise
        except Exception as failure:
            self.manifest["status"] = "failed"
            if self.active_stage:
                self.event(self.active_stage, "failed", str(failure)[:1000])
            raise
        finally:
            if self.manifest["status"] == "started":
                self.manifest["status"] = "ready"
            self.manifest["production_model"] = getattr(self.text, "settings", self.config["text"])["model"]
            self.manifest["usage"] = {"text": self.text.usage, "vision": self.vision.usage if self.vision else {},"acceptance": self.acceptance.usage if getattr(self,'acceptance',None) else {}}
            save_json(self.output / "manifest.json", self.manifest)

    @staticmethod
    def validate_feedback(value):
        if not isinstance(value.get("has_issues"), bool) or not isinstance(value.get("suggested_improvements"), list):
            raise ValueError("视觉评审 JSON 结构不合法")
        if not all(isinstance(item, str) for item in value["suggested_improvements"]):
            raise ValueError("评审意见必须是字符串数组")
