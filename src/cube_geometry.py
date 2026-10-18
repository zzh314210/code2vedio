"""Exact cube-net geometry. Rigid hinges use SciPy Rotation, not LLM coordinates."""
from collections import deque
import numpy as np
from scipy.spatial.transform import Rotation

EXAMPLE = {'A': (-1, 0), 'B': (0, 0), 'C': (1, 0), 'D': (2, 0), 'E': (0, 1), 'F': (0, -1)}
TRANSFER = {**EXAMPLE, 'D': (0, 2)}
DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
CORNERS = np.array([[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]])

def frames(net, amount=1.0, root=None):
    root = root or next(iter(net))
    by_position = {tuple(p): name for name, p in net.items()}
    result = {root: (np.zeros(3), np.array([1., 0, 0]), np.array([0., 1, 0]))}
    pending = deque([root])
    while pending:
        name = pending.popleft()
        center, u, v = result[name]
        x, y = net[name]
        for dx, dy in DIRECTIONS:
            child = by_position.get((x + dx, y + dy))
            if child is None or child in result:
                continue
            direction = dx * u + dy * v
            axis = v if dx else u
            angle = (dx if dx else -dy) * np.pi / 2 * amount
            rotation = Rotation.from_rotvec(axis * angle)
            result[child] = (center + .5 * direction + .5 * rotation.apply(direction), rotation.apply(u), rotation.apply(v))
            pending.append(child)
    if len(result) != len(net):
        raise ValueError('Net must be connected')
    return result

def vertices(frame):
    c, u, v = frame
    return np.array([c + x * u + y * v for x, y in CORNERS])

def edge(frame, side):
    indices = {'bottom': (0, 1), 'right': (1, 2), 'top': (2, 3), 'left': (3, 0)}[side]
    return vertices(frame)[list(indices)]

def same_edge(a, b):
    return np.allclose(a, b, atol=1e-7) or np.allclose(a, b[::-1], atol=1e-7)

def canonical(cells):
    variants = []
    for flip in (1, -1):
        for rotation in range(4):
            transformed = []
            for x, y in cells:
                x, y = x * flip, y
                for _ in range(rotation):
                    x, y = -y, x
                transformed.append((x, y))
            left = min(x for x, y in transformed)
            bottom = min(y for x, y in transformed)
            variants.append(tuple(sorted((x-left, y-bottom) for x, y in transformed)))
    return min(variants)

def cube_nets():
    shapes = {((0, 0),)}
    for count in range(2, 7):
        expanded = set()
        for cells in shapes:
            for x, y in cells:
                for dx, dy in DIRECTIONS:
                    if (x+dx, y+dy) not in cells:
                        expanded.add(canonical((*cells, (x+dx, y+dy))))
        shapes = expanded
    valid = []
    for cells in sorted(shapes):
        net = {str(i): p for i, p in enumerate(cells)}
        f = frames(net)
        normals = {tuple(np.round(np.cross(u, v)).astype(int)) for c, u, v in f.values()}
        if len(normals) == 6:
            valid.append(cells)
    return valid

def classified_nets():
    groups = {'141': [], '132': [], '222': [], '33': []}
    for net in cube_nets():
        for swap in (False, True):
            cells = [(y,x) if swap else (x,y) for x,y in net]
            rows = [sum(1 for x, yy in cells if yy==y) for y in range(max(y for x,y in cells)+1)]
            key = {(1,1,4):'141', (1,2,3):'132', (2,2,2):'222', (3,3):'33'}.get(tuple(sorted(rows)))
            if key:
                groups[key].append(cells)
                break
        else:
            raise ValueError('Unclassified valid cube net')
    return groups
