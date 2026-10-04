import importlib.util
import textwrap
from pathlib import Path

from manim import Scene, Text, SVGMobject, VGroup, RoundedRectangle, Rectangle, FadeOut, config

from project_extensions import read_extensions


class NarratedScene(Scene):
    lesson_title = ""
    lesson_beats = []
    lesson_font = "Microsoft YaHei"
    lesson_assets = {}
    lesson_credits = ""
    lesson_style = {}

    def asset(self, key):
        if key not in self.lesson_assets:
            raise ValueError("未授权素材 key")
        return SVGMobject(self.lesson_assets[key]).set_height(1.5)

    def scene_text(self, text, font_size=30, color=None):
        default = "#203C36" if self.lesson_style.get("theme") == "light" else "#FFFFFF"
        return Text(text, font=self.lesson_font, font_size=font_size, color=color or default)

    def extension(self, name, *args, **kwargs):
        runtime = Path(__file__).resolve().parent
        entries = read_extensions(runtime)
        if name not in entries:
            raise ValueError("未注册的项目扩展: " + str(name))
        if not hasattr(self, "_extension_cache"):
            self._extension_cache = {}
        if name not in self._extension_cache:
            entry = entries[name]
            spec = importlib.util.spec_from_file_location("project_extension_" + name, runtime / entry["file"])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            function = getattr(module, entry["entrypoint"], None)
            if not callable(function):
                raise ValueError("项目扩展入口不是可调用函数: " + name)
            self._extension_cache[name] = function
        return self._extension_cache[name](self, *args, **kwargs)

    def begin_beat(self, index):
        self.clear()
        beat = self.lesson_beats[index]
        self._beat_start = self.renderer.time
        self._beat_duration = beat["duration"]
        self._beat_index = index
        light = self.lesson_style.get("theme") == "light"
        portrait = self.lesson_style.get("orientation") == "portrait"
        width = config.frame_width - 1.1
        top = config.frame_height / 2
        accent = "#287D68" if light else "#58C4DD"
        muted = "#627A73" if light else "#94A3B8"
        brand = self.scene_text(self.lesson_style.get("brand", "教学 · 可视化课堂"), 16, muted)
        brand.move_to([0, top - 0.38, 0])
        title = self.scene_text(self.lesson_title, 29 if portrait else 32, accent)
        if title.width > width:
            title.scale_to_fit_width(width)
        title.move_to([0, top - 0.92, 0])
        rail = Rectangle(width=width, height=0.025, stroke_width=0, fill_color=muted, fill_opacity=0.15)
        rail.move_to([0, top - 1.38, 0])
        progress_width = width * (index + 1) / len(self.lesson_beats)
        progress = Rectangle(width=progress_width, height=0.035, stroke_width=0, fill_color=accent, fill_opacity=1)
        progress.move_to([-(width - progress_width) / 2, top - 1.38, 0])
        bottom = -top
        caption_y = bottom + 0.73
        plate = RoundedRectangle(width=width, height=0.94, corner_radius=0.18, stroke_width=0, fill_color="#FFFFFF" if light else "#172034", fill_opacity=0.97)
        plate.move_to([0, caption_y, 0])
        self._chrome = VGroup(brand, title, rail, progress, plate)
        cues = beat.get("subtitles") or [{"start": 0, "end": beat["duration"], "text": beat["caption"]}]
        for cue in cues:
            caption = self.scene_text("\n".join(textwrap.wrap(cue["text"], width=20 if portrait else 32)), 25 if portrait else 26)
            if caption.width > width - 0.45:
                caption.scale_to_fit_width(width - 0.45)
            if caption.height > 0.74:
                caption.scale_to_fit_height(0.74)
            caption.move_to([0, caption_y, 0])
            caption.set_opacity(0)
            caption.add_updater(lambda mob, cue=cue: mob.set_opacity(int(cue["start"] <= self.renderer.time - self._beat_start < cue["end"])))
            self._chrome.add(caption)
        if self.lesson_credits:
            credit = self.scene_text(self.lesson_credits, 10, muted)
            if credit.width > width:
                credit.scale_to_fit_width(width)
            credit.move_to([0, bottom + 0.13, 0])
            self._chrome.add(credit)
        self.add(self._chrome)

    def remaining(self):
        return max(0.0, self._beat_duration - (self.renderer.time - self._beat_start))

    def play(self, *animations, **kwargs):
        remaining = self.remaining()
        if remaining < 1 / config.frame_rate - 0.00001:
            return
        prepared = self.compile_animations(*animations, **kwargs)
        if prepared and max(animation.run_time for animation in prepared) > remaining:
            kwargs["run_time"] = remaining
        return super().play(*prepared, **kwargs)

    def wait(self, duration=1, **kwargs):
        remaining = min(float(duration), self.remaining())
        if remaining >= 1 / config.frame_rate - 0.00001:
            return super().wait(remaining, **kwargs)

    def end_beat(self):
        content = [mob for mob in self.mobjects if mob is not self._chrome]
        remaining = self.remaining()
        if content and remaining >= 0.3:
            super().wait(max(0, remaining - 0.3))
            super().play(*[FadeOut(mob) for mob in content], run_time=0.3)
        elif remaining >= 1 / config.frame_rate - 0.00001:
            super().wait(remaining)
