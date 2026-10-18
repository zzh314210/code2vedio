"""Offline adapters for Rough.js and Perfect Freehand, independent of subject matter."""
import json
import math
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
import numpy as np
from manim import VGroup, VMobject, Polygon


@lru_cache(maxsize=512)
def _paths(payload):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Handdrawn rendering needs Node.js; install it on the render worker.")
    result = subprocess.run([node, str(Path(__file__).with_name("handdrawn_bridge.cjs"))],
                            input=payload, capture_output=True, text=True, encoding="utf8", timeout=20)
    if result.returncode:
        raise RuntimeError("Handdrawn library failed: " + result.stderr[-1000:])
    return json.loads(result.stdout)


def _points(points, minimum=2):
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] not in (2, 3) or not minimum <= len(array) <= 2048 or not np.isfinite(array).all():
        raise ValueError("Expected finite 2D/3D points, count 2..2048")
    return array


def sketch_shape(scene, kind, width=2, height=1, points=None, center=(0, 0, 0), color=None, fill=None, seed=37):
    if kind not in {"rectangle", "ellipse", "polygon", "curve", "line", "arrow"}:
        raise ValueError("Unknown sketch shape")
    if not all(math.isfinite(v) and 0 < v <= 40 for v in (width, height)):
        raise ValueError("Invalid sketch dimensions")
    center = np.asarray(center, dtype=float)
    if center.shape != (3,) or not np.isfinite(center).all():
        raise ValueError("Invalid sketch center")
    data = [] if points is None else (_points(points, 3 if kind == "polygon" else 2)[:, :2] * 100).tolist()
    if kind in {"line", "arrow"}:
        if len(data) != 2 or np.linalg.norm(np.asarray(data[1]) - data[0]) < .1:
            raise ValueError("Line/arrow requires two distinct points")
    if kind in {"polygon", "curve"} and not data:
        raise ValueError("This shape requires points")
    ink = color or scene.style_color("primary")
    options = dict(seed=int(seed), roughness=.7, bowing=.5, strokeWidth=2.1, stroke=ink,
                   fillStyle="hachure", hachureGap=7, fillWeight=.8)
    if fill:
        options["fill"] = fill
    paths = _paths(json.dumps(dict(kind=kind, width=width*100, height=height*100, points=data, options=options), sort_keys=True))
    group = VGroup()
    for entry in paths["sets"]:
        path = VMobject()
        for op in entry["ops"]:
            p = np.asarray(op["data"], dtype=float).reshape(-1, 2) / 100
            coords = [np.array([x, y, 0]) for x, y in p]
            if op["op"] == "move": path.start_new_path(coords[0])
            elif op["op"] == "lineTo": path.add_line_to(coords[0])
            elif op["op"] == "bcurveTo": path.add_cubic_bezier_curve_to(*coords)
            else: raise ValueError("Unknown Rough.js path operation")
        if entry["type"] == "fillPath": path.set_fill(fill, opacity=1).set_stroke(width=0)
        else: path.set_stroke(fill if entry["type"] == "fillSketch" else ink, width=.8 if entry["type"] == "fillSketch" else 2.1)
        group.add(path)
    return group.shift(center)


def ink_path(scene, points, color=None, width=.05):
    if not math.isfinite(width) or not .005 <= width <= .3:
        raise ValueError("Ink width must be .005..0.3 scene units")
    points = _points(points)
    data = points.copy()
    data[:, :2] *= 100
    if data.shape[1] == 3 and ((data[:, 2] < 0).any() or (data[:, 2] > 1).any()):
        raise ValueError("Stroke pressure must be 0..1")
    result = _paths(json.dumps(dict(kind="ink", points=data.tolist(), size=width*100, simulatePressure=points.shape[1] == 2), sort_keys=True))
    if len(result["outline"]) < 3:
        raise ValueError("Ink stroke too short")
    return Polygon(*[[x/100,y/100,0] for x,y in result["outline"]], stroke_width=0,
                   fill_color=color or scene.style_color("primary"), fill_opacity=1)
