"""Modelo da cena: diagnósticos, entidades, referências e resolução de alvos."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import layout as L
from . import vocab as V

SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
REF = re.compile(r"^([a-z][a-z0-9_]*)(?:\.([a-z_]+))?$")


@dataclass
class Diagnostic:
    """Erro ou aviso estruturado: campo, valor recebido, valores aceitos, sugestão."""

    level: str  # "error" | "warning"
    path: str
    message: str
    got: object = None
    accepted: list | None = None
    hint: str | None = None
    fix: dict | None = None      # correção aplicável por máquina: {path, value} ou {path, rename}

    def to_dict(self) -> dict:
        d = {"level": self.level, "path": self.path, "message": self.message}
        if self.got is not None:
            d["got"] = self.got
        if self.accepted is not None:
            d["accepted"] = self.accepted
        if self.hint:
            d["hint"] = self.hint
        if self.fix:
            d["fix"] = self.fix
        return d

    def __str__(self) -> str:
        tag = "ERRO" if self.level == "error" else "AVISO"
        out = f"[{tag}] {self.path}: {self.message}"
        if self.got is not None:
            out += f" (recebido: {self.got!r})"
        if self.accepted is not None:
            shown = ", ".join(str(a) for a in self.accepted[:12])
            more = "…" if len(self.accepted) > 12 else ""
            out += f" (aceitos: {shown}{more})"
        if self.hint:
            out += f" → {self.hint}"
        return out


class RefError(ValueError):
    def __init__(self, message: str, accepted: list | None = None):
        super().__init__(message)
        self.accepted = accepted


@dataclass
class Entity:
    id: str
    kind: str
    label: str
    desc: str
    plane: str
    box: tuple[float, float, float, float]
    orient: str | None = None
    brightness: str = "normal"
    saturation: str = "normal"
    tags: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def center(self) -> tuple[float, float]:
        return L.box_center(self.box)

    @property
    def brightness_rank(self) -> int:
        return V.LEVELS.index(self.brightness)

    @property
    def saturation_rank(self) -> int:
        return V.SATURATION_LEVELS.index(self.saturation)


@dataclass
class Target:
    """Alvo resolvido de uma referência: entidade, âncora, região ou ponto."""

    kind: str  # "entity" | "region" | "point"
    id: str
    anchor: str | None
    entity: Entity | None
    point: tuple[float, float]
    box: tuple[float, float, float, float] | None

    @property
    def is_point(self) -> bool:
        return self.kind == "point" or (self.kind == "entity" and self.anchor is not None)


class Scene:
    def __init__(self, data: dict, entities: list[Entity]):
        self.data = data
        self.entities = entities
        self.by_id = {e.id: e for e in entities}
        self.name = data["scene"]
        canvas = data["canvas"]
        self.canvas_shape = canvas.get("shape", "rect")
        self.ratio = L.parse_ratio(canvas["ratio"])
        self.grid_kind = data["grid"]["kind"]

    def to_universal_ir(self):
        """Return the additive destination-neutral scene representation."""
        from .universal_ir import from_scene
        return from_scene(self)

    # ---- referências -------------------------------------------------
    def resolve(self, ref: str) -> Target:
        m = REF.match(str(ref).strip())
        if not m:
            raise RefError(f"referência malformada: {ref!r} (use entidade, entidade.âncora, região ou ponto)")
        name, anchor = m.group(1), m.group(2)
        if name in V.POINT_NAMES:
            if anchor:
                raise RefError(f"o ponto {name!r} não tem âncoras: {ref!r}")
            return Target("point", name, None, None, L.point_xy(self.grid_kind, name), None)
        if name in L.region_names():
            if anchor:
                raise RefError(f"a região {name!r} não tem âncoras: {ref!r}")
            box = L.region_box(self.grid_kind, name)
            return Target("region", name, None, None, L.box_center(box), box)
        ent = self.by_id.get(name)
        if ent is None:
            raise RefError(
                f"referência a algo que não existe: {name!r}",
                accepted=sorted(self.by_id) + V.POINT_NAMES_LIST,
            )
        if anchor is None:
            return Target("entity", name, None, ent, ent.center, ent.box)
        if anchor not in V.ANCHORS:
            raise RefError(f"âncora desconhecida: {anchor!r}", accepted=list(V.ANCHORS))
        if anchor in V.DYNAMIC_ANCHORS and not ent.orient:
            raise RefError(
                f"a âncora {anchor!r} de {name!r} exige `orient` na entidade",
                accepted=list(V.DIRECTIONS),
            )
        pt = L.anchor_xy(ent.box, ent.orient, anchor)
        return Target("entity", name, anchor, ent, pt, ent.box)

    def focal_target(self) -> Target:
        return self.resolve(self.data["intent"]["focal"])

    def in_canvas(self, pt: tuple[float, float]) -> bool:
        return L.canvas_contains(self.canvas_shape, self.ratio, pt[0], pt[1])


# Lista fixa usada nas mensagens de erro de referência.
V.POINT_NAMES_LIST = list(V.POINT_NAMES) + L.region_names()


def build_scene(data: dict) -> Scene:
    """Constrói a cena a partir de dados já validados."""
    grid_kind = data["grid"]["kind"]
    entities: list[Entity] = []
    for spec in data["entities"]:
        entities.append(
            Entity(
                id=spec["id"],
                kind=spec["kind"],
                label=spec["label"],
                desc=spec["desc"],
                plane=spec["plane"],
                box=L.entity_box(spec, grid_kind),
                orient=spec.get("orient"),
                brightness=spec.get("brightness", "normal"),
                saturation=spec.get("saturation", "normal"),
                tags=list(spec.get("tags", [])),
                details=list(spec.get("details", [])),
            )
        )
    return Scene(data, entities)
