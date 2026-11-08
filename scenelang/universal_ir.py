"""Universal Scene IR: representação serializável independente de renderer.

É uma API experimental aditiva: cenas YAML existentes continuam sendo a fonte
compatível; ``from_scene`` faz uma projeção explícita para o esquema v1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

SCHEMA_VERSION = "1.0.0"


@dataclass
class UniversalScene:
    schema_version: str = SCHEMA_VERSION
    id: str = "scene"
    coordinate_system: dict[str, Any] = field(default_factory=lambda: {
        "dimension": 2, "units": "normalized", "handedness": "not_applicable",
        "up_axis": "y", "origin": "top_left", "x_direction": "right", "y_direction": "down",
    })
    entities: list[dict[str, Any]] = field(default_factory=list)
    geometry: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    materials: list[dict[str, Any]] = field(default_factory=list)
    lighting: list[dict[str, Any]] = field(default_factory=list)
    camera: dict[str, Any] = field(default_factory=dict)
    temporal: dict[str, Any] = field(default_factory=dict)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


def from_scene(scene) -> UniversalScene:
    """Map known SceneLang fields and preserve unprojected data in metadata."""
    data = scene.data
    entities = []
    geometry = []
    for ent in scene.entities:
        entities.append({"id": ent.id, "kind": ent.kind, "label": ent.label,
                         "description": ent.desc, "plane": ent.plane,
                         "tags": list(ent.tags), "properties": {
                             "orientation": ent.orient, "brightness": ent.brightness,
                             "saturation": ent.saturation, "details": list(ent.details)}})
        x, y, w, h = ent.box
        geometry.append({"entity": ent.id, "type": "box2", "coordinates": [x, y, w, h], "space": "scene"})
    relations = list(data.get("interactions") or [])
    constraints = [{"language": "scenelang.assert", "expression": x} for x in data.get("asserts", [])]
    constraints += [{"language": "scenelang.verify", "expression": x} for x in data.get("verify", [])]
    return UniversalScene(
        id=str(data.get("scene", "scene")), entities=entities, geometry=geometry,
        relations=relations, materials=list((data.get("materials") or {}).items()) if isinstance(data.get("materials"), dict) else list(data.get("materials") or []),
        lighting=list(data.get("lights") or []), camera=dict(data.get("camera") or {}),
        temporal=dict(data.get("temporal") or {}), constraints=constraints,
        metadata={"source": "SceneLang", "source_version": data.get("version"),
                  "canvas": data.get("canvas"), "grid": data.get("grid"),
                  "unmapped_fields": {k: data[k] for k in ("style", "intent", "palette", "background", "atmosphere") if k in data}},
    )


def validate_ir(value: UniversalScene | dict[str, Any]) -> list[dict[str, str]]:
    """Return stable path/message diagnostics for required IR invariants."""
    d = value.to_dict() if isinstance(value, UniversalScene) else value
    out: list[dict[str, str]] = []
    def err(path, message): out.append({"path": path, "message": message})
    if not isinstance(d, dict): return [{"path": "$", "message": "must be an object"}]
    if d.get("schema_version") != SCHEMA_VERSION: err("$.schema_version", f"must equal {SCHEMA_VERSION}")
    cs = d.get("coordinate_system")
    if not isinstance(cs, dict) or cs.get("dimension") not in (2, 3): err("$.coordinate_system.dimension", "must be 2 or 3")
    ids = []
    entities = d.get("entities", [])
    if not isinstance(entities, list):
        err("$.entities", "must be an array")
        entities = []
    for i, e in enumerate(entities):
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"]: err(f"$.entities[{i}].id", "must be a non-empty string")
        else: ids.append(e["id"])
    if len(ids) != len(set(ids)): err("$.entities", "entity ids must be unique")
    geometry = d.get("geometry", [])
    if not isinstance(geometry, list):
        err("$.geometry", "must be an array")
        geometry = []
    for i, g in enumerate(geometry):
        if not isinstance(g, dict) or g.get("entity") not in ids: err(f"$.geometry[{i}].entity", "must reference an entity")
        if isinstance(g, dict) and g.get("type") == "box2":
            c = g.get("coordinates")
            if not isinstance(c, list) or len(c) != 4 or not all(isinstance(n, (int, float)) for n in c) or c[2] <= 0 or c[3] <= 0:
                err(f"$.geometry[{i}].coordinates", "box2 requires [x, y, width, height] with positive size")
    for key in ("relations", "materials", "lighting", "constraints"):
        rows = d.get(key, [])
        if not isinstance(rows, list):
            err(f"$.{key}", "must be an array")
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                err(f"$.{key}[{i}]", "must be an object")
            elif key == "relations":
                for field_name in ("source", "target"):
                    ref = row.get(field_name)
                    if ref is not None and ref not in ids:
                        err(f"$.relations[{i}].{field_name}", "must reference an entity")
    for key in ("camera", "temporal", "metadata"):
        if not isinstance(d.get(key, {}), dict):
            err(f"$.{key}", "must be an object")
    return out


@dataclass
class AdapterReport:
    adapter: str
    supported: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    losses: list[dict[str, str]] = field(default_factory=list)


class SceneAdapter(Protocol):
    name: str
    def capabilities(self) -> set[str]: ...
    def export(self, scene: UniversalScene) -> Any: ...


def adapter_report(scene: UniversalScene, adapter: SceneAdapter) -> AdapterReport:
    features = {"entities", "geometry", "relations", "materials", "lighting", "camera", "temporal", "constraints"}
    caps = adapter.capabilities()
    supported, unsupported = sorted(features & caps), sorted(features - caps)
    losses = [{"feature": key, "reason": "adapter does not declare support"} for key in unsupported]
    return AdapterReport(adapter.name, supported, unsupported, losses)
