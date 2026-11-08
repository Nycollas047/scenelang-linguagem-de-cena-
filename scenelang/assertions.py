"""Asserts: condições verificáveis sobre a cena (e, depois, sobre a imagem).

Sintaxe:  nome(arg, arg)  ou  nome(arg) OP número  ou  focal_single
Exemplos: above(spear.tip, warrior.shoulder) | count(ally) == 2 | near(spear.tip, pt_ul, 0.05)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import layout as L
from . import vocab as V
from . import zones
from .model import RefError, Scene

ARITY = {
    "above": (2, 2),
    "below": (2, 2),
    "left_of": (2, 2),
    "right_of": (2, 2),
    "inside": (2, 2),
    "near": (2, 3),
    "count": (1, 1),
    "visible": (1, 1),
    "facing": (2, 2),
    "brightest": (1, 1),
    "focal_single": (0, 0),
    "clear_zone": (1, 1),
    "line_of_sight": (2, 2),
    "occluded": (2, 3),
    "no_overlap": (2, 2),
    "clearance": (3, 3),
    "connected": (2, 2),
    "reachable": (2, 2),
    "no_softlock": (2, 2),
    "min_paths": (2, 2),
}
GRAPH_PREDICATES = ("connected", "reachable", "no_softlock", "min_paths")
REF_ARGS = {  # quais argumentos são referências
    "above": (0, 1),
    "below": (0, 1),
    "left_of": (0, 1),
    "right_of": (0, 1),
    "inside": (0, 1),
    "near": (0, 1),
    "visible": (0,),
    "facing": (0,),
    "brightest": (0,),
    "line_of_sight": (0, 1),
    "occluded": (0, 1, 2),
    "clearance": (0, 1),
    "connected": (0, 1),
    "reachable": (0, 1),
    "no_softlock": (0, 1),
    "min_paths": (0, 1),
}
NEAR_DEFAULT_TOL = 0.06

_PATTERN = re.compile(
    r"^\s*([a-z_]+)\s*(?:\((.*)\))?\s*(?:(==|!=|>=|<=|>|<)\s*(\d+))?\s*$"
)


class AssertSyntaxError(ValueError):
    pass


@dataclass
class Assert:
    raw: str
    name: str
    args: list[str]
    op: str | None = None
    num: int | None = None


def parse_assert(raw: str) -> Assert:
    m = _PATTERN.match(str(raw))
    if not m:
        raise AssertSyntaxError(f"sintaxe inválida: {raw!r}")
    name, argtxt, op, num = m.group(1), m.group(2), m.group(3), m.group(4)
    if name not in V.PREDICATES:
        raise AssertSyntaxError(f"predicado desconhecido: {name!r}")
    args = [a.strip() for a in argtxt.split(",")] if argtxt and argtxt.strip() else []
    lo, hi = ARITY[name]
    if not lo <= len(args) <= hi:
        raise AssertSyntaxError(
            f"{name} espera {lo if lo == hi else f'{lo} a {hi}'} argumento(s), recebeu {len(args)}"
        )
    if name in ("count", "min_paths") and op is None:
        raise AssertSyntaxError(f"{name} exige comparação, por exemplo: " + ("count(ally) == 2" if name == "count" else "min_paths(a, b) >= 2"))
    if name not in ("count", "min_paths") and op is not None:
        raise AssertSyntaxError(f"{name} não aceita comparação numérica")
    if name == "facing" and args[1] not in V.DIRECTIONS:
        raise AssertSyntaxError(f"direção desconhecida: {args[1]!r}")
    if name == "clearance":
        try:
            if float(args[2]) < 0:
                raise ValueError
        except ValueError:
            raise AssertSyntaxError(f"distância mínima inválida: {args[2]!r} (use um número ≥ 0, em alturas do quadro)") from None
    if name == "near" and len(args) == 3:
        try:
            float(args[2])
        except ValueError:
            raise AssertSyntaxError(f"tolerância inválida: {args[2]!r}") from None
    return Assert(str(raw), name, args, op, int(num) if num is not None else None)


def group(scene: Scene, key: str) -> list:
    """Entidades de um grupo: o id de uma entidade, ou uma etiqueta/tipo (`cover`, `door`, `prop`)."""
    if key in scene.by_id:
        return [scene.by_id[key]]
    return [e for e in scene.entities if e.kind == key or key in e.tags]


def check_refs(scene: Scene, a: Assert) -> None:
    """Levanta RefError se algum argumento-referência não resolver."""
    for i in REF_ARGS.get(a.name, ()):
        if a.name == "clearance" and i == 2:
            continue
        scene.resolve(a.args[i])
    if a.name == "no_overlap":
        for key in a.args:
            if not group(scene, key):
                known = sorted(set(scene.by_id) | {e.kind for e in scene.entities} | {t for e in scene.entities for t in e.tags})
                raise RefError(f"no_overlap({key}): nem entidade, nem tipo, nem etiqueta com esse nome", accepted=known)
    if a.name in GRAPH_PREDICATES:
        from . import topology

        if not topology.edges(scene.data):
            raise RefError(f"{a.name} exige a seção `graph` com arestas")
        for arg in a.args[:2]:
            if topology.node_of(scene, arg.split(".")[0]) is None:
                raise RefError(f"{arg!r} não é um nó do grafo nem está dentro de um", accepted=topology.node_ids(scene.data))
    if a.name == "clear_zone":
        if a.args[0] not in zones.zones(scene.data):
            raise RefError(f"clear_zone({a.args[0]}): nenhuma zona com esse id em safe_zones", accepted=sorted(zones.zones(scene.data)))
    if a.name == "count":
        key = a.args[0]
        known = {e.kind for e in scene.entities} | {t for e in scene.entities for t in e.tags}
        if key not in known:
            raise RefError(f"count({key}): nenhuma entidade com esse tipo ou etiqueta", accepted=sorted(known))


@dataclass
class Result:
    raw: str
    ok: bool
    detail: str


def _cmp(op: str, left: int, right: int) -> bool:
    return {
        "==": left == right,
        "!=": left != right,
        ">=": left >= right,
        "<=": left <= right,
        ">": left > right,
        "<": left < right,
    }[op]


def _xy(p: tuple[float, float]) -> str:
    return f"({p[0]:.3f}, {p[1]:.3f})"


def evaluate(scene: Scene, a: Assert) -> Result:
    n = a.name
    if n in ("above", "below", "left_of", "right_of"):
        p, q = scene.resolve(a.args[0]).point, scene.resolve(a.args[1]).point
        if n == "above":
            ok, rel = p[1] < q[1], f"y {p[1]:.3f} < {q[1]:.3f}"
        elif n == "below":
            ok, rel = p[1] > q[1], f"y {p[1]:.3f} > {q[1]:.3f}"
        elif n == "left_of":
            ok, rel = p[0] < q[0], f"x {p[0]:.3f} < {q[0]:.3f}"
        else:
            ok, rel = p[0] > q[0], f"x {p[0]:.3f} > {q[0]:.3f}"
        return Result(a.raw, ok, rel)

    if n == "inside":
        t, host = scene.resolve(a.args[0]), scene.resolve(a.args[1])
        if host.box is None:
            return Result(a.raw, False, "o alvo externo não tem caixa")
        if t.is_point:
            ok = L.point_in_box(t.point, host.box)
            return Result(a.raw, ok, f"ponto {_xy(t.point)} {'dentro' if ok else 'fora'} da caixa de {host.id}")
        ok = L.box_inside(t.box, host.box)
        return Result(a.raw, ok, f"caixa de {t.id} {'cabe' if ok else 'não cabe'} na caixa de {host.id}")

    if n == "near":
        p, q = scene.resolve(a.args[0]).point, scene.resolve(a.args[1]).point
        tol = float(a.args[2]) if len(a.args) == 3 else NEAR_DEFAULT_TOL
        d = L.distance(p, q, scene.ratio)
        return Result(a.raw, d <= tol, f"distância {d:.3f} (limite {tol:g}, em alturas do quadro)")

    if n == "count":
        key = a.args[0]
        found = [e.id for e in scene.entities if e.kind == key or key in e.tags]
        return Result(a.raw, _cmp(a.op, len(found), a.num), f"{len(found)} encontrado(s): {', '.join(found) or '-'}")

    if n == "visible":
        t = scene.resolve(a.args[0])
        if t.is_point:
            ok = scene.in_canvas(t.point)
            return Result(a.raw, ok, f"ponto {_xy(t.point)} {'dentro' if ok else 'fora'} do quadro")
        bad = [c for c in L.box_corners(t.box) if not scene.in_canvas(c)]
        return Result(a.raw, not bad, "caixa inteira dentro do quadro" if not bad else f"{len(bad)} canto(s) fora do quadro")

    if n == "facing":
        ent = scene.resolve(a.args[0]).entity
        ok = ent is not None and ent.orient == a.args[1]
        return Result(a.raw, ok, f"orient de {a.args[0]} = {ent.orient if ent else None!r}, esperado {a.args[1]!r}")

    if n == "brightest":
        ent = scene.resolve(a.args[0]).entity
        others = [e for e in scene.entities if e is not ent]
        bright = all(ent.brightness_rank > e.brightness_rank for e in others)
        sat = all(ent.saturation_rank >= e.saturation_rank for e in others)
        return Result(
            a.raw,
            bright and sat,
            f"brilho {ent.brightness}, saturação {ent.saturation}; "
            + ("único com brilho máximo" if bright else "outro elemento empata ou passa no brilho")
            + ("" if sat else "; outro elemento é mais saturado"),
        )

    if n == "focal_single":
        maxed = [e.id for e in scene.entities if e.brightness == "max"]
        focal = scene.focal_target().entity
        ok = len(maxed) == 1 and focal is not None and maxed[0] == focal.id
        return Result(a.raw, ok, f"brilho máximo em: {', '.join(maxed) or '-'}; foco em {focal.id if focal else '-'}")

    if n == "clear_zone":
        z = zones.zones(scene.data)[a.args[0]]
        bad = zones.offenders(scene, z)
        return Result(a.raw, not bad, "zona livre" if not bad else "invadida por " + ", ".join(f"{i} ({f:.0%} da caixa)" for i, f in bad))

    if n in ("line_of_sight", "occluded"):
        pa, pb = scene.resolve(a.args[0]), scene.resolve(a.args[1])
        skip = {a.args[0].split(".")[0], a.args[1].split(".")[0]}
        blockers = [e for e in scene.entities if e.id not in skip and set(e.tags) & set(V.SIGHT_BLOCKER_TAGS)]
        hit = [e.id for e in blockers if L.segment_intersects_box(pa.point, pb.point, e.box)]
        if n == "line_of_sight":
            return Result(a.raw, not hit, "nada bloqueia a linha" if not hit else "bloqueada por " + ", ".join(hit))
        if len(a.args) == 3:
            bl = a.args[2].split(".")[0]
            hit_b = bl in [e.id for e in blockers if L.segment_intersects_box(pa.point, pb.point, e.box)]
            return Result(a.raw, hit_b, f"{bl} intercepta a linha" if hit_b else f"{bl} não intercepta a linha" + (f" (bloqueia: {', '.join(hit)})" if hit else " (a linha está livre)"))
        return Result(a.raw, bool(hit), "protegida por " + ", ".join(hit) if hit else "a linha de visão está livre")

    if n == "no_overlap":
        ga, gb = group(scene, a.args[0]), group(scene, a.args[1])
        seen, bad = set(), []
        for x in ga:
            for y in gb:
                key = tuple(sorted((x.id, y.id)))
                if x is not y and key not in seen:
                    seen.add(key)
                    if L.boxes_overlap(x.box, y.box):
                        bad.append(f"{x.id}×{y.id}")
        return Result(a.raw, not bad, f"{len(seen)} par(es) sem sobreposição" if not bad else "sobrepõem: " + ", ".join(bad))

    if n == "clearance":
        ta, tb = scene.resolve(a.args[0]), scene.resolve(a.args[1])
        if ta.box is None or tb.box is None:
            return Result(a.raw, False, "o alvo não tem caixa")
        need = float(a.args[2])
        d = L.box_clearance(ta.box, tb.box, scene.ratio)
        return Result(a.raw, d >= need - 1e-9, f"folga {d:.3f} (mínimo {need:g}, em alturas do quadro)")

    if n in GRAPH_PREDICATES:
        from . import topology

        if n == "connected":
            ok, why = topology.connected(scene, *a.args)
        elif n == "reachable":
            ok, why = topology.reachable(scene, *a.args)
        elif n == "no_softlock":
            ok, why = topology.no_softlock(scene, *a.args)
        else:
            k, why = topology.max_paths(scene, *a.args)
            ok = _cmp(a.op, k, a.num)
        return Result(a.raw, ok, why)

    return Result(a.raw, False, "predicado sem avaliador")


def evaluate_all(scene: Scene) -> list[Result]:
    return [evaluate(scene, parse_assert(raw)) for raw in scene.data.get("asserts", [])]
