import importlib.util
import textwrap
import re
import numpy as np
from pathlib import Path

from manim import Scene, Text, SVGMobject, ImageMobject, VGroup, VMobject, RoundedRectangle, Rectangle, FadeOut, config

from project_extensions import read_extensions
from manimpango import list_fonts

_AVAILABLE_FONTS = set(list_fonts())
_MATH_FONT = next((name for name in ("Arial", "DejaVu Sans", "Noto Sans") if name in _AVAILABLE_FONTS), "sans-serif")
_SYMBOL_FONT = "Segoe UI Symbol" if "Segoe UI Symbol" in _AVAILABLE_FONTS else _MATH_FONT


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
        path = Path(self.lesson_assets[key])
        if path.suffix.lower() == ".svg":
            return SVGMobject(str(path)).set_height(1.5)
        return ImageMobject(str(path)).set_height(1.5)

    def sketch_line(self, start, end, color=None, width=3, arrow=False):
        start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
        if start.shape != (3,) or end.shape != (3,) or not np.isfinite([start, end]).all():
            raise ValueError("Sketch endpoints must be finite 3D points")
        direction = end - start
        length = np.linalg.norm(direction)
        if length < 0.001 or not 0 < width <= 12:
            raise ValueError("Invalid sketch length or width")
        normal = np.array([-direction[1], direction[0], 0.0]) / length
        ink = color or (self.lesson_style.get("style_palette") or {}).get("foreground", "#29332F")
        strokes = VGroup()
        for phase, opacity in ((0.0, 1.0), (1.9, 0.32)):
            points = [start + direction * fraction + normal * (0.018 * np.sin(fraction * 15 + phase) * np.sin(np.pi * fraction)) for fraction in np.linspace(0, 1, 17)]
            stroke = VMobject().set_points_smoothly(points).set_stroke(ink, width=width, opacity=opacity)
            strokes.add(stroke)
        if arrow:
            unit = direction / length
            size = min(0.24, length * 0.2)
            for sign in (-1, 1):
                tip = VMobject().set_points_as_corners([end - unit * size + normal * sign * size * 0.5, end])
                strokes.add(tip.set_stroke(ink, width=width))
        return strokes

    def scene_text(self, text, font_size=30, color=None):
        default = "#203C36" if self.lesson_style.get("theme") == "light" else "#FFFFFF"
        default = (self.lesson_style.get("style_palette") or {}).get("foreground", default)
        # CJK display fonts may omit mathematical symbols; preserve the series face
        # while rendering only those glyphs with an installed symbol font.
        # Keep each mathematical run in one font so mixed baselines do not
        # turn a minus into an apparent underscore. Chinese keeps its style face.
        fallback = {f'[{m.start()}:{m.end()}]': _MATH_FONT for m in re.finditer(r'[A-Za-z0-9 .,+*/=()％%−×÷≥≤≠≈∞∑√→←↔⇒:;!?\-]+', text)}
        fallback.update({glyph: _SYMBOL_FONT for glyph in '①②③④⑤⑥⑦⑧⑨' if glyph in text})
        return Text(text, font=self.lesson_font, font_size=font_size, color=color or default, t2f=fallback)

    def scene_paragraph(self, text, width, font_size=28, color=None, line_spacing=0.16):
        """Wrap shaped CJK/Latin lines without shrinking the requested font size."""
        if width <= 0:
            raise ValueError('Paragraph width must be positive')
        lines = []
        for paragraph in text.split('\n'):
            rest = paragraph
            while rest:
                low, high = 1, len(rest)
                while low < high:
                    mid = (low + high + 1) // 2
                    if self.scene_text(rest[:mid], font_size, color).width <= width * .985:
                        low = mid
                    else:
                        high = mid - 1
                if low < len(rest) and re.match(r'[A-Za-z0-9.%]', rest[low - 1]) and re.match(r'[A-Za-z0-9.%]', rest[low]):
                    token = re.search(r'[A-Za-z0-9.%]+$', rest[:low])
                    if token and token.start() > 0:
                        low = token.start()
                if low < len(rest) and rest[low] in '，。；：！？）】、' and low > 1:
                    low -= 1
                lines.append(rest[:low])
                rest = rest[low:]
        group = VGroup(*[self.scene_text(line, font_size, color) for line in lines])
        group.arrange([0, -1, 0], aligned_edge=[-1, 0, 0], buff=line_spacing)
        return group

    def sketch_shape(self, kind, **kwargs):
        from handdrawn_runtime import sketch_shape
        return sketch_shape(self, kind, **kwargs)

    def ink_path(self, points, **kwargs):
        from handdrawn_runtime import ink_path
        return ink_path(self, points, **kwargs)

    def style_color(self, role="primary"):
        palette = self.lesson_style.get("style_palette") or {}
        if role not in palette:
            raise ValueError("Unknown style color role: " + str(role))
        return palette[role]

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
        if index == 0 or self.lesson_style.get("reset_between_beats", True):
            self.clear()
        elif hasattr(self, "_chrome"):
            self.remove(self._chrome)
        beat = self.lesson_beats[index]
        self._beat_start = self.renderer.time
        self._beat_duration = beat["duration"]
        self._beat_index = index
        light = self.lesson_style.get("theme") == "light"
        portrait = self.lesson_style.get("orientation") == "portrait"
        width = config.frame_width - 1.1
        top = config.frame_height / 2
        accent = "#287D68" if light else "#58C4DD"
        accent = (self.lesson_style.get("style_palette") or {}).get("primary", accent)
        muted = (self.lesson_style.get("style_palette") or {}).get("muted", "#627A73" if light else "#94A3B8")
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
        plate = RoundedRectangle(width=width, height=0.94, corner_radius=0.18, stroke_width=0, fill_color=(self.lesson_style.get("style_palette") or {}).get("panel", "#FFFFFF" if light else "#172034"), fill_opacity=0.97)
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
        layout = self.lesson_style.get("layout") or "classic"
        if layout == "minimal":
            self._chrome.remove(brand, rail, progress)
        elif layout == "canvas":
            self._chrome.remove(brand, title, rail, progress, plate)
        elif layout != "classic":
            raise ValueError("Unknown scene layout")
        self._chrome.set_z_index(100)
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
        kwargs.setdefault("frozen_frame", False)
        remaining = min(float(duration), self.remaining())
        if remaining >= 1 / config.frame_rate - 0.00001:
            return super().wait(remaining, **kwargs)

    def end_beat(self):
        content = [mob for mob in self.mobjects if mob is not self._chrome]
        remaining = self.remaining()
        if content and remaining >= 0.3 and self.lesson_style.get("exit_fade", True) and self.lesson_style.get("reset_between_beats", True):
            super().wait(max(0, remaining - 0.3), frozen_frame=False)
            super().play(*[FadeOut(mob) for mob in content], run_time=0.3)
        elif remaining >= 1 / config.frame_rate - 0.00001:
            super().wait(remaining, frozen_frame=False)
