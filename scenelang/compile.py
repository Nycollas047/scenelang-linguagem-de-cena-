"""Compilador: cena -> representação intermediária (IR) -> backend.

Backends:
  prose    texto em português, ordenado por prioridade (para modelos só de texto)
  json     o mesmo conteúdo em JSON estruturado (prioridades no topo)
  regions  caixas, pesos e prompts por região (para modelos com controle de layout)
"""
from __future__ import annotations

import json

from . import layout as L
from . import phrases as P
from . import vocab as V
from .assertions import parse_assert
from .model import Entity, Scene
from .negations import to_affirmation

PLANE_ORDER = ("foreground", "midground", "background")
KIND_PT = {
    "character": "personagem", "creature": "criatura", "prop": "objeto", "structure": "estrutura",
    "terrain": "terreno", "sky": "céu", "effect": "efeito", "light_source": "fonte de luz", "vehicle": "veículo",
}
WEIGHT = {"low": 0.6, "normal": 1.0, "high": 1.2, "max": 1.5}


def _ordered_asserts(scene: Scene) -> tuple[list[str], list[str]]:
    raws = list(scene.data.get("asserts", []))
    boost = [b for b in scene.data.get("priority_boost", []) if b in raws]
    rest = [r for r in raws if r not in boost]
    return boost, rest


def priorities(scene: Scene) -> tuple[list[str], list[str]]:
    """(lista de prioridades, lembrete final com os itens reforçados)."""
    out: list[str] = []
    focal_ref = scene.data["intent"]["focal"]
    where = P.position_of_point(scene.grid_kind, scene.focal_target().point)
    out.append(f"O ponto focal é único: {P.target_phrase(scene, focal_ref)}, {where}.")
    boost, rest = _ordered_asserts(scene)
    reminders: list[str] = []
    for raw in boost + rest:
        a = parse_assert(raw)
        if a.name == "focal_single":
            continue
        statement = P.assert_texts(scene, a)[0]
        if raw in boost:
            statement = "(reforço) " + statement
            reminders.append(P.assert_texts(scene, a)[0])
        out.append(statement)
    return out, reminders


def entity_sentence(scene: Scene, e: Entity) -> str:
    where = P.entity_position(e, scene.grid_kind)
    sep = ", " if where.startswith("com ") else " "
    parts = [f"{P.cap(e.label)}{sep}{where}: {e.desc}."]
    if e.orient:
        parts.append(f"Orientação: {V.DIRECTION_PT[e.orient]} ({P.SCREEN_NOTE}).")
    if e.brightness == "max":
        parts.append("É o elemento mais brilhante e mais saturado da imagem.")
    elif e.brightness == "low" or e.saturation == "muted":
        parts.append("Permanece discreto: baixa saturação e brilho contido.")
    parts.extend(f"{d}." if not d.endswith(".") else d for d in e.details)
    return " ".join(parts)


def light_sentence(scene: Scene, li: dict) -> str:
    role = V.LIGHT_ROLE_PT[li["role"]]
    src = scene.resolve(li["source"])
    if src.kind == "entity":
        origin = f"nasce {P.de(P.target_phrase(scene, li['source']))}"
    else:
        origin = f"vem {P.target_position(scene, li['source'])}"
    text = f"{P.cap(role)} {li['color']}: {origin}"
    hits = li.get("hits") or []
    if hits:
        text += "; toca " + " e ".join(P.target_phrase(scene, h) for h in hits)
    if li.get("note"):
        text += f"; {li['note']}"
    return text + "."


def camera_sentence(scene: Scene) -> str | None:
    cam = scene.data.get("camera")
    if not cam:
        return None
    bits = []
    if "angle" in cam:
        bits.append(V.ANGLES[cam["angle"]])
    if "lens" in cam:
        bits.append(V.LENSES[cam["lens"]])
    text = ", ".join(bits)
    if cam.get("focus"):
        sharp = " e ".join(P.em(P.target_phrase(scene, r)) for r in cam["focus"])
        text += ("; " if text else "") + f"nitidez máxima {sharp}"
    if cam.get("depth_blur"):
        text += ("; " if text else "") + cam["depth_blur"]
    return text + "." if text else None


def palette_sentence(scene: Scene) -> str | None:
    pal = scene.data.get("palette")
    if not pal:
        return None
    bits = []
    if pal.get("dominant"):
        bits.append("dominantes " + ", ".join(pal["dominant"]))
    if pal.get("accent"):
        use = f", usado {pal['accent_use']}" if pal.get("accent_use") else ""
        bits.append(f"acento {pal['accent']}{use}")
    bits.extend(pal.get("notes", []))
    return "; ".join(bits) + "." if bits else None


def canvas_sentence(scene: Scene) -> str:
    c = scene.data["canvas"]
    if scene.canvas_shape == "circle":
        return f"Quadro circular (proporção {c['ratio']}): todos os elementos importantes ficam dentro do círculo."
    if scene.canvas_shape == "ellipse":
        return f"Quadro elíptico (proporção {c['ratio']}): elementos importantes dentro da elipse."
    return f"Proporção {c['ratio']}."


def grid_sentence(scene: Scene) -> str:
    kind = "grade áurea" if scene.grid_kind == "golden" else "regra dos terços"
    return f"Composição pela {kind}."


def avoid_affirmations(scene: Scene) -> list[str]:
    out = []
    for text in scene.data.get("avoid", []) or []:
        rule = to_affirmation(text)
        if rule and not rule[1] and rule[0] not in out:
            out.append(rule[0])
    return out


def build_ir(scene: Scene) -> dict:
    d = scene.data
    prios, reminders = priorities(scene)
    style = d["style"]
    style_line = style["base"]
    if style.get("mix"):
        style_line += "; " + P.mix_phrase(style["mix"])
    ir: dict = {
        "prioridades": prios,
        "estilo": style_line,
        "quadro": canvas_sentence(scene),
        "grade": grid_sentence(scene),
    }
    intent = d["intent"]
    if intent.get("emotion") or intent.get("story"):
        ir["intencao"] = " ".join(
            x for x in (
                f"Emoção: {intent['emotion']}." if intent.get("emotion") else "",
                f"História: {intent['story']}." if intent.get("story") else "",
            ) if x
        )
    ir["planos"] = {
        plane: [entity_sentence(scene, e) for e in scene.entities if e.plane == plane]
        for plane in PLANE_ORDER
        if any(e.plane == plane for e in scene.entities)
    }
    if d.get("lights"):
        ir["iluminacao"] = [light_sentence(scene, li) for li in d["lights"]]
    cam = camera_sentence(scene)
    if cam:
        ir["camera"] = cam
    pal = palette_sentence(scene)
    if pal:
        ir["paleta"] = pal
    if d.get("gaze"):
        ir["ordem_do_olhar"] = [P.target_phrase(scene, r) for r in d["gaze"]]
    details = list(d.get("details", [])) + avoid_affirmations(scene)
    if details:
        ir["detalhes"] = details
    if d.get("finish"):
        ir["acabamento"] = d["finish"]
    if reminders:
        ir["lembrete_final"] = reminders
    return ir


# ---------------------------------------------------------------------------
def to_prose(scene: Scene) -> str:
    ir = build_ir(scene)
    lines = [f"Ilustração: {ir['estilo']}. {ir['quadro']} {ir['grade']}", "", "PRIORIDADES (cumpra primeiro):"]
    lines += [f"{i}. {t}" for i, t in enumerate(ir["prioridades"], 1)]
    if "intencao" in ir:
        lines += ["", "INTENÇÃO: " + ir["intencao"]]
    lines += ["", "CENA:"]
    for plane, sentences in ir["planos"].items():
        lines.append(f"{V.PLANE_PT[plane]}:")
        lines += [f"- {s}" for s in sentences]
    if "iluminacao" in ir:
        lines += ["", "ILUMINAÇÃO:"] + [f"- {s}" for s in ir["iluminacao"]]
    if "camera" in ir:
        lines += ["", "CÂMERA: " + ir["camera"]]
    if "paleta" in ir:
        lines += ["", "PALETA: " + ir["paleta"]]
    if "ordem_do_olhar" in ir:
        lines += ["", "ORDEM DO OLHAR: " + " → ".join(f"{i}) {t}" for i, t in enumerate(ir["ordem_do_olhar"], 1)) + "."]
    if "detalhes" in ir:
        lines += ["", "DETALHES: " + "; ".join(ir["detalhes"]) + "."]
    if "acabamento" in ir:
        lines += ["", "ACABAMENTO: " + ir["acabamento"] + "."]
    if "lembrete_final" in ir:
        lines += ["", "LEMBRETE FINAL (crítico):"] + [f"- {t}" for t in ir["lembrete_final"]]
    return "\n".join(lines) + "\n"


def to_json(scene: Scene) -> str:
    ir = build_ir(scene)
    out = {"prioridade_maxima": ir["prioridades"]}
    out.update({k: v for k, v in ir.items() if k != "prioridades"})
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def to_regions(scene: Scene, size: str | None = None) -> str:
    w_px, h_px = L.size_px(scene.ratio, size)
    d = scene.data
    ir = build_ir(scene)
    style = d["style"]
    weights = {k: float(v) / 100.0 for k, v in (style.get("mix") or {}).items()}
    global_bits = [ir["estilo"], ir["quadro"], ir["grade"]]
    for key in ("paleta", "camera"):
        if key in ir:
            global_bits.append(ir[key])
    regions = []
    for e in sorted(scene.entities, key=lambda e: V.PLANES.index(e.plane)):
        x, y, w, h = e.box
        regions.append({
            "id": e.id,
            "label": e.label,
            "kind": e.kind,
            "plane": e.plane,
            "box_norm": [round(v, 4) for v in (x, y, w, h)],
            "box_px": [round(x * w_px), round(y * h_px), round(w * w_px), round(h * h_px)],
            "orient": e.orient,
            "weight": WEIGHT[e.brightness],
            "prompt": e.desc + (f", orientação {V.DIRECTION_PT[e.orient]} ({P.SCREEN_NOTE})" if e.orient else ""),
        })
    fx, fy = scene.focal_target().point
    out = {
        "canvas": {"shape": scene.canvas_shape, "ratio": d["canvas"]["ratio"], "size_px": [w_px, h_px]},
        "global_prompt": " ".join(global_bits),
        "style_weights": weights,
        "focal": {"ref": d["intent"]["focal"], "xy_norm": [round(fx, 4), round(fy, 4)],
                  "xy_px": [round(fx * w_px), round(fy * h_px)]},
        "priorities": ir["prioridades"],
        "regions": regions,
    }
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


BACKENDS = {"prose": to_prose, "json": to_json, "regions": to_regions}
