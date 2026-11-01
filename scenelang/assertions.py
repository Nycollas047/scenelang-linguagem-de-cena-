"""Asserts: condições verificáveis sobre a cena (e, depois, sobre a imagem).

Sintaxe:  nome(arg, arg)  ou  nome(arg) OP número  ou  focal_single
Exemplos: above(spear.tip, warrior.shoulder) | count(ally) == 2 | near(spear.tip, pt_ul, 0.05)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import layout as L
from . import vocab as V
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
}
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
    if name == "count" and op is None:
        raise AssertSyntaxError("count exige comparação, por exemplo: count(ally) == 2")
    if name != "count" and op is not None:
        raise AssertSyntaxError(f"{name} não aceita comparação numérica")
    if name == "facing" and args[1] not in V.DIRECTIONS:
        raise AssertSyntaxError(f"direção desconhecida: {args[1]!r}")
    if name == "near" and len(args) == 3:
        try:
            float(args[2])
        except ValueError:
            raise AssertSyntaxError(f"tolerância inválida: {args[2]!r}") from None
    return Assert(str(raw), name, args, op, int(num) if num is not None else None)


def check_refs(scene: Scene, a: Assert) -> None:
    """Levanta RefError se algum argumento-referência não resolver."""
    for i in REF_ARGS.get(a.name, ()):
        scene.resolve(a.args[i])
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

    return Result(a.raw, False, "predicado sem avaliador")


def evaluate_all(scene: Scene) -> list[Result]:
    return [evaluate(scene, parse_assert(raw)) for raw in scene.data.get("asserts", [])]
