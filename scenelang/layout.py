"""Geometria da cena: grade, regiões, âncoras e formato do quadro.

Todas as coordenadas são normalizadas: x e y em [0, 1], com y crescendo para
baixo (como numa imagem). Direções são sempre do ponto de vista de quem vê a
imagem (esquerda e direita da tela, nunca do personagem).
"""
from __future__ import annotations

import math
import re

from . import vocab as V

GOLDEN = 0.381966  # 1 - 1/phi, a linha áurea a 38,2%


def grid_a(kind: str) -> float:
    return GOLDEN if kind == "golden" else 1.0 / 3.0


def grid_lines(kind: str) -> tuple[float, float, float, float]:
    a = grid_a(kind)
    return (0.0, a, 1.0 - a, 1.0)


def region_names() -> list[str]:
    return [f"{r}_{c}" for r in V.ROW_NAMES for c in V.COL_NAMES]


def region_box(kind: str, name: str) -> tuple[float, float, float, float]:
    row, col = name.split("_", 1)
    ri, ci = V.ROW_NAMES.index(row), V.COL_NAMES.index(col)
    lines = grid_lines(kind)
    x0, x1 = lines[ci], lines[ci + 1]
    y0, y1 = lines[ri], lines[ri + 1]
    return (x0, y0, x1 - x0, y1 - y0)


def point_xy(kind: str, name: str) -> tuple[float, float]:
    a = grid_a(kind)
    return {
        "pt_ul": (a, a),
        "pt_ur": (1.0 - a, a),
        "pt_ll": (a, 1.0 - a),
        "pt_lr": (1.0 - a, 1.0 - a),
    }[name]


def region_of(kind: str, x: float, y: float) -> str:
    lines = grid_lines(kind)
    ci = 0 if x < lines[1] else (1 if x < lines[2] else 2)
    ri = 0 if y < lines[1] else (1 if y < lines[2] else 2)
    return f"{V.ROW_NAMES[ri]}_{V.COL_NAMES[ci]}"


def parse_ratio(text: str) -> float:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", str(text))
    if not m or float(m.group(2)) == 0:
        raise ValueError(f"proporção inválida: {text!r}")
    return float(m.group(1)) / float(m.group(2))


def canvas_contains(shape: str, ratio: float, x: float, y: float, eps: float = 1e-9) -> bool:
    if shape == "circle":
        return ((x - 0.5) * ratio) ** 2 + (y - 0.5) ** 2 <= 0.25 + eps
    if shape == "ellipse":
        return ((x - 0.5) / 0.5) ** 2 + ((y - 0.5) / 0.5) ** 2 <= 1.0 + eps
    return -eps <= x <= 1.0 + eps and -eps <= y <= 1.0 + eps


def box_corners(box):
    x, y, w, h = box
    return [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]


def box_center(box) -> tuple[float, float]:
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


def box_inside(inner, outer, eps: float = 1e-9) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return (
        ix >= ox - eps
        and iy >= oy - eps
        and ix + iw <= ox + ow + eps
        and iy + ih <= oy + oh + eps
    )


def point_in_box(pt, box, eps: float = 1e-9) -> bool:
    x, y, w, h = box
    return x - eps <= pt[0] <= x + w + eps and y - eps <= pt[1] <= y + h + eps


def entity_box(spec: dict, grid_kind: str) -> tuple[float, float, float, float]:
    """Caixa (x, y, w, h) de uma entidade a partir de `box` ou de `at` + `size`."""
    if "box" in spec:
        return tuple(float(v) for v in spec["box"])  # type: ignore[return-value]
    at = spec["at"]
    size = spec.get("size")
    if at in region_names():
        bx = region_box(grid_kind, at)
        if size is None:
            return bx
        cx, cy = box_center(bx)
    else:
        cx, cy = point_xy(grid_kind, at)
        if size is None:
            size = (0.15, 0.15)
    w, h = float(size[0]), float(size[1])
    return (cx - w / 2.0, cy - h / 2.0, w, h)


def anchor_xy(box, orient: str | None, anchor: str) -> tuple[float, float]:
    """Posição de uma âncora na caixa. `tip` e `base` dependem da orientação."""
    x, y, w, h = box
    if anchor in V.DYNAMIC_ANCHORS:
        dx, dy = V.DIRECTIONS[orient or "up"]
        sign = 1.0 if anchor == "tip" else -1.0
        return (x + w / 2.0 + sign * dx * w / 2.0, y + h / 2.0 + sign * dy * h / 2.0)
    fx, fy = V.ANCHORS[anchor]
    return (x + fx * w, y + fy * h)


def distance(a, b, ratio: float) -> float:
    """Distância em unidades de altura do quadro (corrige a proporção)."""
    return math.hypot((a[0] - b[0]) * ratio, a[1] - b[1])


def size_px(ratio: float, size: str | None = None, long_side: int = 1344) -> tuple[int, int]:
    if size:
        m = re.fullmatch(r"(\d+)x(\d+)", size.strip().lower())
        if not m:
            raise ValueError(f"tamanho inválido: {size!r} (use LARGURAxALTURA)")
        return int(m.group(1)), int(m.group(2))
    if ratio >= 1:
        w, h = long_side, long_side / ratio
    else:
        w, h = long_side * ratio, long_side
    return int(round(w / 8) * 8), int(round(h / 8) * 8)


# ---- geometria de gameplay (v0.9) ---------------------------------------------------------------------------
def boxes_overlap(a, b, eps: float = 1e-9) -> bool:
    """As caixas (x, y, w, h) têm interseção de área positiva? Encostar na borda não conta."""
    return min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) > eps and min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) > eps


def box_clearance(a, b, ratio: float = 1.0) -> float:
    """Distância borda a borda entre duas caixas (0 se se tocam ou sobrepõem), em alturas do quadro."""
    dx = max(a[0] - (b[0] + b[2]), b[0] - (a[0] + a[2]), 0.0)
    dy = max(a[1] - (b[1] + b[3]), b[1] - (a[1] + a[3]), 0.0)
    return math.hypot(dx * ratio, dy)


def segment_intersects_box(p1, p2, box, eps: float = 1e-9) -> bool:
    """Liang–Barsky: o segmento p1→p2 cruza (ou toca por dentro) a caixa (x, y, w, h)?"""
    x, y, w, h = box
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p1[0] - x), (dx, x + w - p1[0]), (-dy, p1[1] - y), (dy, y + h - p1[1])):
        if abs(p) < eps:
            if q < -eps:
                return False          # paralelo e fora
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1 + eps
