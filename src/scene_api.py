"""Read custom drawing API signatures without importing the rendering runtime."""
import ast
import inspect
from functools import lru_cache
from pathlib import Path


METHOD_FILES = {
    "scene_text": "scene_runtime.py", "scene_paragraph": "scene_runtime.py",
    "sketch_line": "scene_runtime.py", "style_color": "scene_runtime.py",
    "asset": "scene_runtime.py", "sketch_shape": "handdrawn_runtime.py",
    "ink_path": "handdrawn_runtime.py",
}
SHAPE_HINT = "圆角矩形请使用 Manim 的 RoundedRectangle(width=..., height=..., corner_radius=..., fill_color=..., fill_opacity=..., stroke_color=..., stroke_width=...)。"


@lru_cache(maxsize=64)
def _contract(filename, modified, size, name):
    tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
    function = next((node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name), None)
    if function is None:
        return None  # Older project snapshots may not include every helper.
    parameters = []
    positional = function.args.posonlyargs + function.args.args
    defaults = [None] * (len(positional) - len(function.args.defaults)) + function.args.defaults
    for index, (argument, default) in enumerate(zip(positional, defaults)):
        if index == 0:  # self / scene is supplied by NarratedScene.
            continue
        kind = inspect.Parameter.POSITIONAL_ONLY if index < len(function.args.posonlyargs) else inspect.Parameter.POSITIONAL_OR_KEYWORD
        parameters.append(inspect.Parameter(argument.arg, kind, default=inspect.Parameter.empty if default is None else ast.literal_eval(default)))
    for argument, default in zip(function.args.kwonlyargs, function.args.kw_defaults):
        parameters.append(inspect.Parameter(argument.arg, inspect.Parameter.KEYWORD_ONLY, default=inspect.Parameter.empty if default is None else ast.literal_eval(default)))
    choices = frozenset()
    if name == "sketch_shape":
        for node in ast.walk(function):
            if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "kind"
                    and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotIn) and isinstance(node.comparators[0], ast.Set)):
                choices = frozenset(ast.literal_eval(node.comparators[0]))
                break
    return inspect.Signature(parameters), choices


def contracts(runtime=None):
    root = Path(runtime) if runtime else Path(__file__).parent
    result = {}
    for name, filename in METHOD_FILES.items():
        path = root / filename
        if path.is_file():
            stat = path.stat()
            contract = _contract(str(path.resolve()), stat.st_mtime_ns, stat.st_size, name)
            if contract is not None:
                result[name] = contract
    return result


def reference(runtime=None):
    lines = ["自定义绘图方法的实际接口（来自本项目运行时，不能套用 Manim 构造函数的参数）："]
    for name, (signature, choices) in contracts(runtime).items():
        lines.append(f"self.{name}{signature}" + ("；kind 只能是 " + ", ".join(sorted(choices)) if choices else ""))
    return "\n".join(lines) + "\n" + SHAPE_HINT


def validate_calls(tree, runtime=None):
    available = contracts(runtime)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"
                and node.func.attr in METHOD_FILES):
            continue
        name = node.func.attr
        if name not in available:
            raise ValueError(f"当前项目未提供 self.{name}，请使用本项目提供的方法或 Manim 图形。")
        signature, choices = available[name]
        hint = f"正确接口：self.{name}{signature}。" + (SHAPE_HINT if name == "sketch_shape" else "")
        if any(isinstance(arg, ast.Starred) for arg in node.args) or any(kw.arg is None for kw in node.keywords):
            raise ValueError(f"self.{name} 请直接填写参数，不能用 *args/**kwargs。{hint}")
        try:
            bound = signature.bind(*node.args, **{kw.arg: kw.value for kw in node.keywords})
        except TypeError as error:
            raise ValueError(f"self.{name} 参数不兼容：{error}。{hint}") from error
        if choices:
            kind = bound.arguments.get("kind")
            if not isinstance(kind, ast.Constant) or kind.value not in choices:
                raise ValueError(f"self.{name} 的 kind 必须直接填写以下名称之一：{', '.join(sorted(choices))}。{SHAPE_HINT}")
