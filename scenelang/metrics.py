"""Métrica de level design (`guides.metrics`): converte células da `canvas.pixel_grid` em metros e confere medidas mínimas.

guides:
  metrics:
    cell_size: 0.5            # metros por célula (1 célula = largura do quadro ÷ pixel_grid)
    door_width_cells: 3       # entidades com tag `door` precisam de ao menos esta passagem
    corridor_min_cells: 4     # tag `corridor`: a menor dimensão
    cover_min_cells: 2        # tag `cover`: a maior dimensão

As células são quadradas: na horizontal 1 célula = 1/N da largura; na vertical = ratio/N da altura.
Um aviso traz `fix` com a caixa já corrigida (mesmo centro, lado estreito alargado até o mínimo).
"""
from __future__ import annotations

import math

from . import vocab as V

KEYS = {"unit", "cell_size", "door_width_cells", "corridor_min_cells", "cover_min_cells"}
RULES = (("door", "door_width_cells", "largura da passagem"), ("corridor", "corridor_min_cells", "largura do corredor"),
         ("cover", "cover_min_cells", "tamanho da cobertura"))


def settings(data: dict) -> dict:
    g = data.get("guides")
    m = g.get("metrics") if isinstance(g, dict) else None
    return m if isinstance(m, dict) else {}


def cell_size(data: dict) -> float:
    v = settings(data).get("cell_size", 1.0)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 1.0


def grid_cells(scene) -> int | None:
    n = scene.data.get("canvas", {}).get("pixel_grid")
    return int(n) if isinstance(n, int) and not isinstance(n, bool) else None


def cells_of(box, ratio: float, n: int) -> tuple[float, float]:
    """(células na horizontal, células na vertical) de uma caixa."""
    return box[2] * n, box[3] * n / ratio


def _span(entity, tag: str, cx: float, cy: float) -> tuple[str, float]:
    """Qual dimensão conta para a regra: passagem de porta (perpendicular à orientação), menor lado do corredor, maior da cobertura."""
    if tag == "cover":
        return ("x", cx) if cx >= cy else ("y", cy)
    if tag == "door" and entity.orient and V.DIRECTIONS[entity.orient] != (0, 0):
        dx, dy = V.DIRECTIONS[entity.orient]
        return ("y", cy) if abs(dx) >= abs(dy) else ("x", cx)       # porta virada para os lados: a passagem é a altura
    return ("x", cx) if cx <= cy else ("y", cy)


def check(c, data: dict, scene) -> None:
    g = data.get("guides")
    m = g.get("metrics") if isinstance(g, dict) else None
    if m is None:
        return
    if not isinstance(m, dict):
        c.error("$.guides.metrics", "deve ser um mapa", got=m)
        return
    for k in m:
        if k not in KEYS:
            c.error(f"$.guides.metrics.{k}", "campo desconhecido", got=k, accepted=sorted(KEYS))
    for k in KEYS - {"unit"}:
        if k in m and not (isinstance(m[k], (int, float)) and not isinstance(m[k], bool) and m[k] > 0):
            c.error(f"$.guides.metrics.{k}", "deve ser um número positivo", got=m[k])
    if "unit" in m and not isinstance(m["unit"], str):
        c.error("$.guides.metrics.unit", "deve ser um texto (ex.: meter)", got=m["unit"])
    if scene is None:
        return
    n = grid_cells(scene)
    if n is None:
        c.error("$.guides.metrics", "metrics exige canvas.pixel_grid (a célula é a unidade de medida)")
        return
    idx = {e.get("id"): i for i, e in enumerate(data.get("entities") or []) if isinstance(e, dict)}
    for e in scene.entities:
        for tag, key, what in RULES:
            need = m.get(key)
            if tag not in e.tags or not isinstance(need, (int, float)):
                continue
            cx, cy = cells_of(e.box, scene.ratio, n)
            axis, have = _span(e, tag, cx, cy)
            if have + 1e-9 >= need:
                continue
            x, y, w, h = e.box
            if axis == "x":
                nw = math.ceil(need / n * 1e4) / 1e4          # arredonda PARA CIMA: a caixa corrigida nunca fica abaixo do mínimo
                fix_box = [round(x + w / 2 - nw / 2, 4), y, nw, h]
            else:
                nh = math.ceil(need * scene.ratio / n * 1e4) / 1e4
                fix_box = [x, round(y + h / 2 - nh / 2, 4), w, nh]
            meters = f" ({have * cell_size(data):.2f} m de {need * cell_size(data):.2f} m)"
            fix = {"path": f"$.entities[{idx[e.id]}].box", "value": fix_box} if e.id in idx and "box" in (data["entities"][idx[e.id]]) else None
            c.warn(f"entity:{e.id}", f"{what} de {e.id} tem {have:.1f} célula(s); o mínimo é {need:g}{meters}", got=round(have, 2),
                   hint=f"alargue a caixa para {fix_box}")
            if fix is not None:
                c.items[-1].fix = fix
