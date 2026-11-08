"""Açúcar sintático da v0.8: expande atalhos em primitivas que o resto do compilador já conhece.

Aplicado em `load_text` depois da normalização e ANTES da validação (como `normalize`); nunca dentro de `validate_data`.
O YAML do autor não muda: só a cópia em memória. Cada expansão vira uma nota legível e, se falhar, um diagnóstico.

  pose.preset            → `pose.joints` preenchido com a pose-base; o que a cena escreve sobrescreve eixo a eixo
  entities[].at (mapa)   → `box` calculada + asserts topológicos (right_of/left_of/above/below) que a posição implica
  auto_asserts           → `asserts` sintetizados a partir das caixas (ordem horizontal e vertical do primeiro plano)
  safe_zones             → um assert `clear_zone(id)` por zona (a zona fica livre de elementos)
"""
from __future__ import annotations

import copy
import re

from . import layout as L
from . import vocab as V
from .model import Diagnostic

AUTO_KINDS = {"horizontal_order": "horizontal", "vertical_order": "vertical", "foreground_above": "vertical"}
AUTO_MIN_GAP = 0.08          # separação mínima entre centros para a ordem valer como intenção (e não ruído)
AUTO_PLANES = ("foreground", "midground")
AUTO_SKIP_KINDS = ("terrain", "sky")
REL_KEYS = ("right_of", "left_of", "above", "below")
AT_KEYS = {"anchor", "of", "offset", "gap", "align_x", "align_y", *REL_KEYS}
ALIGN_X, ALIGN_Y = ("left", "center", "right"), ("top", "center", "bottom")
_REF = re.compile(r"^([a-z][a-z0-9_]*)(?:\.([a-z_]+))?$")


def _err(diags, path, msg, **kw):
    diags.append(Diagnostic("error", path, msg, **kw))


def apply(data) -> tuple[object, list[Diagnostic], list[str]]:
    """(dados expandidos, diagnósticos de erro, notas). Dados que não são mapa passam intactos."""
    if not isinstance(data, dict):
        return data, [], []
    d = copy.deepcopy(data)
    diags: list[Diagnostic] = []
    notes: list[str] = []
    ents = d.get("entities")
    if isinstance(ents, list):
        _presets(d, ents, diags, notes)
        _relative(d, ents, diags, notes)
    _safe_zones(d, diags, notes)
    _auto_asserts(d, ents if isinstance(ents, list) else [], diags, notes)
    return d, diags, notes


# ---- pose.preset ----------------------------------------------------------------------------------------------
def _presets(d, ents, diags, notes):
    from . import pose_presets as PP

    for i, e in enumerate(ents):
        po = e.get("pose") if isinstance(e, dict) else None
        if not isinstance(po, dict) or "preset" not in po:
            continue
        if po["preset"] not in PP.PRESETS:
            _err(diags, f"$.entities[{i}].pose.preset", "preset de pose desconhecido", got=po["preset"], accepted=PP.names())
            po.pop("preset")
            continue
        name = po["preset"]
        e["pose"] = PP.resolve(po)
        notes.append(f"entities[{i}].pose.preset {name!r} → juntas preenchidas ({len(e['pose']['joints'])})")


# ---- entities[].at relativo -----------------------------------------------------------------------------------
def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _known_box(e: dict, grid_kind: str):
    """Caixa de uma entidade já resolvida (com `box`, ou `at` textual + `size`), senão None."""
    try:
        if isinstance(e.get("box"), list) and len(e["box"]) == 4 and all(_num(v) for v in e["box"]):
            return tuple(float(v) for v in e["box"])
        if isinstance(e.get("at"), str) and (e["at"] in V.POINT_NAMES or e["at"] in L.region_names()):
            return L.entity_box({"at": e["at"], "size": e.get("size")}, grid_kind)
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _ref_point(ref, boxes, ents_by_id, grid_kind):
    """Ponto de uma referência (ponto da grade, região ou entidade[.âncora]) com o que já se sabe; None se ainda não dá."""
    m = _REF.match(str(ref).strip())
    if not m:
        raise ValueError(f"referência malformada: {ref!r}")
    name, anchor = m.group(1), m.group(2)
    if name in V.POINT_NAMES:
        return L.point_xy(grid_kind, name)
    if name in L.region_names():
        return L.box_center(L.region_box(grid_kind, name))
    if name not in ents_by_id:
        raise ValueError(f"referência a algo que não existe: {name!r}")
    box = boxes.get(name)
    if box is None:
        return None
    if anchor is None:
        return L.box_center(box)
    if anchor not in V.ANCHORS:
        raise ValueError(f"âncora desconhecida: {anchor!r}")
    orient = ents_by_id[name].get("orient")
    if anchor in V.DYNAMIC_ANCHORS and not orient:
        raise ValueError(f"a âncora {anchor!r} de {name!r} exige `orient`")
    return L.anchor_xy(box, orient, anchor)


def _place(at: dict, size, boxes, ents_by_id, grid_kind):
    """Caixa (x, y, w, h) de `at`; None se depende de entidade ainda sem caixa; levanta ValueError se inválido."""
    w, h = float(size[0]), float(size[1])
    rel = [k for k in REL_KEYS if k in at]
    modes = [k for k in ("anchor", "of") if k in at] + rel
    if len(modes) != 1:
        raise ValueError("`at` precisa de exatamente um destes: anchor, of, right_of, left_of, above, below")
    gap = float(at.get("gap", 0.0))
    off = at.get("offset", [0.0, 0.0])
    if not (isinstance(off, list) and len(off) == 2 and all(_num(v) for v in off)):
        raise ValueError("`offset` deve ser [dx, dy] numérico")
    if not _num(gap) or gap < 0:
        raise ValueError("`gap` deve ser um número ≥ 0")
    if modes[0] in ("anchor", "of"):
        pt = _ref_point(at[modes[0]], boxes, ents_by_id, grid_kind)
        if pt is None:
            return None, [at[modes[0]].split(".")[0]]
        return (pt[0] + off[0] - w / 2, pt[1] + off[1] - h / 2, w, h), [at[modes[0]].split(".")[0]]
    key = rel[0]
    tgt = str(at[key]).split(".")[0]
    if tgt not in ents_by_id:
        raise ValueError(f"referência a algo que não existe: {tgt!r}")
    tb = boxes.get(tgt)
    if tb is None:
        return None, [tgt]
    tx, ty, tw, th = tb
    ax, ay = at.get("align_x", "center"), at.get("align_y", "center")
    if key in ("right_of", "left_of"):
        x = tx + tw + gap if key == "right_of" else tx - gap - w
        if isinstance(ay, str) and ay in ALIGN_Y:
            y = {"top": ty, "center": ty + th / 2 - h / 2, "bottom": ty + th - h}[ay]
        else:                                           # referência de âncora: o centro vertical cai nela
            pt = _ref_point(ay, boxes, ents_by_id, grid_kind)
            if pt is None:
                return None, [tgt, str(ay).split(".")[0]]
            y = pt[1] - h / 2
    else:
        y = ty - gap - h if key == "above" else ty + th + gap
        if isinstance(ax, str) and ax in ALIGN_X:
            x = {"left": tx, "center": tx + tw / 2 - w / 2, "right": tx + tw - w}[ax]
        else:
            pt = _ref_point(ax, boxes, ents_by_id, grid_kind)
            if pt is None:
                return None, [tgt, str(ax).split(".")[0]]
            x = pt[0] - w / 2
    return (x + off[0], y + off[1], w, h), [tgt]


def _relative(d, ents, diags, notes):
    grid_kind = (d.get("grid") or {}).get("kind", "golden") if isinstance(d.get("grid"), dict) else "golden"
    pend = [(i, e) for i, e in enumerate(ents) if isinstance(e, dict) and isinstance(e.get("at"), dict)]
    if not pend:
        return
    by_id = {e["id"]: e for e in ents if isinstance(e, dict) and isinstance(e.get("id"), str)}
    boxes = {k: b for k, e in by_id.items() if (b := _known_box(e, grid_kind)) is not None}
    derived: list[str] = []
    progress = True
    while pend and progress:
        progress, rest = False, []
        for i, e in pend:
            p = f"$.entities[{i}].at"
            at = e["at"]
            bad = sorted(set(at) - AT_KEYS)
            if bad:
                _err(diags, p, "campo desconhecido em `at`", got=bad[0], accepted=sorted(AT_KEYS))
                e.pop("at")
                progress = True
                continue
            size = e.get("size")
            if not (isinstance(size, list) and len(size) == 2 and all(_num(v) and v > 0 for v in size)):
                _err(diags, f"$.entities[{i}].size", "`at` em mapa exige `size: [largura, altura]` positivos", got=size)
                e.pop("at")
                progress = True
                continue
            try:
                box, deps = _place(at, size, boxes, by_id, grid_kind)
            except (ValueError, TypeError) as ex:
                _err(diags, p, str(ex), got=at)
                e.pop("at")
                progress = True
                continue
            if box is None:
                rest.append((i, e))
                continue
            progress = True
            rel = next((k for k in REL_KEYS if k in at), None)
            if rel:
                derived.append(f"{rel}({e['id']}, {str(at[rel]).split('.')[0]})")
            e["box"] = [round(v, 4) for v in box]
            boxes[e["id"]] = tuple(e["box"])
            notes.append(f"entities[{i}].at → box {e['box']}")
            e.pop("at")
        pend = rest
    for i, e in pend:
        _err(diags, f"$.entities[{i}].at", "dependência circular ou sem caixa: a posição de {0!r} depende de entidades sem posição".format(e.get("id")), got=e["at"])
        e.pop("at")
    if derived:
        asserts = d.setdefault("asserts", [])
        if isinstance(asserts, list):
            for raw in derived:
                if raw not in asserts:
                    asserts.append(raw)
            notes.append("asserts topológicos derivados de `at`: " + ", ".join(derived))


# ---- safe_zones -----------------------------------------------------------------------------------------------
def _safe_zones(d, diags, notes):
    zones = d.get("safe_zones")
    if not isinstance(zones, list):
        return
    asserts = d.setdefault("asserts", [])
    if not isinstance(asserts, list):
        return
    for z in zones:
        if isinstance(z, dict) and isinstance(z.get("id"), str):
            raw = f"clear_zone({z['id']})"
            if raw not in asserts:
                asserts.append(raw)
                notes.append(f"safe_zones: assert {raw} acrescentado")


# ---- auto_asserts ---------------------------------------------------------------------------------------------
def _equiv(raw: str) -> str:
    """Forma canônica de left_of/right_of/above/below para detectar duplicata invertida."""
    m = re.fullmatch(r"\s*(left_of|right_of|above|below)\(\s*([^,]+?)\s*,\s*([^,]+?)\s*\)\s*", raw)
    if not m:
        return raw.strip()
    n, a, b = m.groups()
    return {"right_of": f"left_of({b},{a})", "below": f"above({b},{a})"}.get(n, f"{n}({a},{b})")


def _auto_asserts(d, ents, diags, notes):
    auto = d.get("auto_asserts")
    if auto is None:
        return
    if not isinstance(auto, list) or not all(isinstance(x, str) for x in auto):
        return                       # o validador acusa o formato
    grid_kind = (d.get("grid") or {}).get("kind", "golden") if isinstance(d.get("grid"), dict) else "golden"
    main = []
    for e in ents:
        if not isinstance(e, dict) or e.get("plane") not in AUTO_PLANES or e.get("kind") in AUTO_SKIP_KINDS:
            continue
        b = _known_box(e, grid_kind)
        if b is not None and isinstance(e.get("id"), str):
            main.append((e["id"], L.box_center(b)))
    asserts = d.setdefault("asserts", [])
    if not isinstance(asserts, list):
        return
    have = {_equiv(a) for a in asserts if isinstance(a, str)}
    added = []
    for name in auto:
        axis = AUTO_KINDS.get(name)
        if axis is None:
            continue                 # nome desconhecido: erro no validador
        idx, pred = (0, "left_of") if axis == "horizontal" else (1, "above")
        order = sorted(main, key=lambda t: t[1][idx])
        for (a, pa), (b, pb) in zip(order, order[1:]):
            if pb[idx] - pa[idx] < AUTO_MIN_GAP:
                continue
            raw = f"{pred}({a}, {b})"
            if _equiv(raw) not in have:
                asserts.append(raw)
                have.add(_equiv(raw))
                added.append(raw)
    if added:
        notes.append("auto_asserts → " + ", ".join(added))
