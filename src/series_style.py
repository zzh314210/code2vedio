"""Topic-neutral visual contract. Does not contain lesson content or layouts."""
import ast
import re


def validate_style_snippet(code, video):
    if not video or not video.get("style_lock"):
        return
    palette = video.get("style_palette", {})
    colors = {value.lower() for value in palette.values()}
    tree = ast.parse(code)
    assignments = {node.targets[0].id: node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}

    def approved_color(node, seen=frozenset()):
        if isinstance(node, ast.Constant):
            return node.value is None or (isinstance(node.value, str) and node.value.lower() in colors)
        if isinstance(node, (ast.Tuple, ast.List)):
            return bool(node.elts) and all(approved_color(x, seen) for x in node.elts)
        if isinstance(node, ast.Name) and node.id in assignments and node.id not in seen:
            return approved_color(assignments[node.id], seen | {node.id})
        if isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self" and node.func.attr == "style_color"):
                return (len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value in palette and not node.keywords)
            if isinstance(node.func, ast.Name) and node.func.id == "interpolate_color":
                return len(node.args) == 3 and all(approved_color(x, seen) for x in node.args[:2])
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.fullmatch(r"#[0-9a-fA-F]{3,8}", node.value) and node.value.lower() not in colors:
                raise ValueError("Style palette is locked; use self.style_color(role) instead of " + node.value)
        if isinstance(node, ast.Name) and re.fullmatch(r"(?:WHITE|BLACK|GRAY|GREY|RED|GREEN|BLUE|YELLOW|PURPLE|PINK|ORANGE|TEAL|GOLD|MAROON)(?:_[A-E])?", node.id):
            raise ValueError("Use self.style_color(role), not Manim color constant " + node.id)
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in {"font", "font_size", "t2f", "t2c", "t2g", "gradient"}:
                    if keyword.arg == "font_size":
                        continue
                    raise ValueError("Keep the series typography and palette; use self.scene_text and self.style_color")
                if keyword.arg and (keyword.arg == "color" or keyword.arg.endswith("_color") or keyword.arg == "fill"):
                    if not approved_color(keyword.value):
                        raise ValueError("Color must come from self.style_color(role) or the selected palette")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"scene_text", "sketch_line"}:
                if len(node.args) > 2 and not approved_color(node.args[2]):
                    raise ValueError("Positional colors must also use the series palette")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"set_color", "set_fill", "set_stroke", "set_color_by_gradient"}:
                args = node.args if node.func.attr == "set_color_by_gradient" else node.args[:1]
                if any(not approved_color(x) for x in args):
                    raise ValueError("Color methods must use the selected series palette")


def apply_style_defaults(video, font):
    """Called inside the isolated render process; shapes remain freely generated."""
    from manim import VMobject, Text, MarkupText, Paragraph
    palette = video["style_palette"]
    VMobject.set_default(color=palette["foreground"], stroke_width=2)
    for cls in (Text, MarkupText, Paragraph):
        cls.set_default(font=font, color=palette["foreground"])
