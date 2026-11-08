"""Exportadores de level design: a planta da cena vira diagrama (Mermaid), mapa 2D (Tiled) ou blockout 3D (Godot, Unity).

  scenelang level CENA --export mermaid|tiled|godot|unity --out ARQUIVO

Unidades: a célula é a largura do quadro ÷ `canvas.pixel_grid` (obrigatório para tiled/godot/unity) e vale `guides.metrics.cell_size`
metros (1 m se ausente). Altura dos blocos 3D por etiqueta (floor 0,2 · half_cover 1,0 · full_cover 2,2 · door 2,2 · wall 3,0), senão
por plano (background 0,2 · midground 1,2 · foreground 0,3 a 3,0 m de altura do chão, como teto). É blockout de MEDIDAS, não geometria
final. LDtk não é suportado (falha com erro claro, em vez de gerar um arquivo que ninguém validou).

Os formatos seguem a documentação pública de cada ferramenta; só o JSON (Tiled/Unity) e o Mermaid são conferidos por testes
automáticos aqui. O `.tscn` do Godot não foi aberto no Godot: confira na sua versão (escrito para o formato 3 do Godot 4).
"""
from __future__ import annotations

import json

from . import metrics as MT
from . import topology as TP

TARGETS = ("mermaid", "tiled", "godot", "unity")
TAG_HEIGHT = {"floor": (0.2, 0.0), "half_cover": (1.0, 0.0), "full_cover": (2.2, 0.0), "door": (2.2, 0.0), "wall": (3.0, 0.0), "overhead": (0.3, 3.0)}
PLANE_HEIGHT = {"background": (0.2, 0.0), "midground": (1.2, 0.0), "foreground": (0.3, 3.0)}
ROLE_FILL = {"spawn": "#bbf7d0", "boss": "#fecaca", "reward": "#fde68a", "secret": "#e9d5ff", "flank": "#bfdbfe", "hub": "#e5e7eb"}


class ExportError(ValueError):
    pass


def _need_grid(scene) -> int:
    n = MT.grid_cells(scene)
    if n is None:
        raise ExportError("este destino exige canvas.pixel_grid (a célula é a unidade do mapa)")
    return n


def _rows(scene, n: int) -> int:
    return max(1, round(n / scene.ratio))


def _height(e) -> tuple[float, float]:
    for t in ("wall", "full_cover", "half_cover", "door", "floor", "overhead"):
        if t in e.tags:
            return TAG_HEIGHT[t]
    return PLANE_HEIGHT[e.plane]


def mermaid(scene) -> str:
    ids = TP.node_ids(scene.data)
    if not ids:
        raise ExportError("sem `graph`: não há nós nem arestas para o diagrama")
    roles = {n["id"]: n.get("role") for n in (scene.data.get("graph") or {}).get("nodes", []) if isinstance(n, dict) and "id" in n}
    g = scene.data["graph"]
    lines = ["flowchart LR"]
    for i in ids:
        label = scene.by_id[i].label if i in scene.by_id else i
        role = f"<br/>({roles[i]})" if roles.get(i) else ""
        shape = f'{i}(["{label}{role}"])' if i in (g.get("spawn"), g.get("goal")) else f'{i}["{label}{role}"]'
        lines.append("    " + shape)
    for e in TP.edges(scene.data):
        kind = e.get("kind", "bidirectional")
        via = scene.by_id[e["via"]].label if e.get("via") in scene.by_id else (e.get("via") or "")
        text = via + (f" 🔒 {scene.by_id[e['unlocked_by']].label}" if kind == "locked" and e.get("unlocked_by") in scene.by_id else "")
        arrow = {"bidirectional": "<-->", "one_way": "-->", "locked": "-.->", "destructible": "-.->", "hazard": "==>"}[kind]
        lines.append(f'    {e["from"]} {arrow}' + (f'|"{text}"|' if text else "") + f' {e["to"]}')
    for i in ids:
        if roles.get(i) in ROLE_FILL:
            lines.append(f"    style {i} fill:{ROLE_FILL[roles[i]]}")
    return "\n".join(lines) + "\n"


def tiled(scene) -> str:
    """Mapa ortogonal do Tiled (JSON) com uma camada de objetos por plano; propriedades: tags, orient, desc, kind."""
    n = _need_grid(scene)
    rows, ts = _rows(scene, n), 32
    layers, oid = [], 1
    for lid, plane in enumerate(("background", "midground", "foreground"), 1):
        objs = []
        for e in scene.entities:
            if e.plane != plane:
                continue
            x, y, w, h = e.box
            props = [{"name": "kind", "type": "string", "value": e.kind}, {"name": "tags", "type": "string", "value": ",".join(e.tags)},
                     {"name": "desc", "type": "string", "value": e.desc}]
            if e.orient:
                props.append({"name": "orient", "type": "string", "value": e.orient})
            objs.append({"id": oid, "name": e.id, "type": e.kind, "x": round(x * n * ts, 3), "y": round(y * n * ts, 3),
                         "width": round(w * n * ts, 3), "height": round(h * n * ts, 3), "rotation": 0, "visible": True, "properties": props})
            oid += 1
        layers.append({"id": lid, "name": plane, "type": "objectgroup", "draworder": "topdown", "objects": objs, "opacity": 1, "visible": True, "x": 0, "y": 0})
    doc = {"type": "map", "version": "1.10", "tiledversion": "1.10.2", "orientation": "orthogonal", "renderorder": "right-down",
           "width": n, "height": rows, "tilewidth": ts, "tileheight": ts, "infinite": False, "nextlayerid": len(layers) + 1,
           "nextobjectid": oid, "layers": layers, "tilesets": [],
           "properties": [{"name": "scene", "type": "string", "value": scene.name}, {"name": "cell_size_m", "type": "float", "value": MT.cell_size(scene.data)}]}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _blocks(scene):
    n = _need_grid(scene)
    rows, cs = _rows(scene, n), MT.cell_size(scene.data)
    out = []
    for e in scene.entities:
        x, y, w, h = e.box
        hz, elev = _height(e)
        out.append({"id": e.id, "label": e.label, "tags": list(e.tags), "plane": e.plane,
                    "center": (round((x + w / 2) * n * cs, 4), round(elev + hz / 2, 4), round((y + h / 2) * rows * cs, 4)),
                    "size": (round(w * n * cs, 4), round(hz, 4), round(h * rows * cs, 4))})
    return out


def godot(scene) -> str:
    """Cena `.tscn` (Godot 4) com um CSGBox3D por entidade; X/Z vêm da planta, Y da altura por etiqueta/plano."""
    lines = ["[gd_scene format=3]", "", f'[node name="{_node(scene.name)}" type="Node3D"]', ""]
    used: set[str] = set()
    for b in _blocks(scene):
        name = _node(b["id"])
        while name in used:
            name += "_"
        used.add(name)
        cx, cy, cz = b["center"]
        sx, sy, sz = b["size"]
        lines += [f'[node name="{name}" type="CSGBox3D" parent="."]',
                  f"transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {cx}, {cy}, {cz})", f"size = Vector3({sx}, {sy}, {sz})",
                  f'metadata/scenelang_tags = "{",".join(b["tags"])}"', ""]
    return "\n".join(lines)


def _node(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in s) or "Level"


def unity(scene) -> str:
    """JSON de blocos (centro e tamanho em metros) para um script do editor instanciar cubos de blockout."""
    doc = {"scene": scene.name, "unit": "meter", "cell_size": MT.cell_size(scene.data), "axes": "x=direita da planta, y=altura, z=para baixo na planta",
           "blocks": [{"name": b["id"], "label": b["label"], "tags": b["tags"], "plane": b["plane"],
                       "position": dict(zip("xyz", b["center"])), "scale": dict(zip("xyz", b["size"]))} for b in _blocks(scene)]}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def export(scene, target: str) -> str:
    if target == "ldtk":
        raise ExportError("ldtk não é suportado: o formato é extenso e não há como validá-lo aqui; use tiled ou o JSON do unity")
    if target not in TARGETS:
        raise ExportError(f"destino desconhecido: {target!r} (use {', '.join(TARGETS)})")
    return {"mermaid": mermaid, "tiled": tiled, "godot": godot, "unity": unity}[target](scene)
