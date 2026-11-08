"""Compilador: cena -> representação intermediária (IR) -> backend.

Backends:
  prose    texto em português, ordenado por prioridade (para modelos só de texto)
  json     o mesmo conteúdo em JSON estruturado (prioridades no topo)
  regions  caixas, pesos e prompts por região (para modelos com controle de layout)
"""
from __future__ import annotations

import json

from . import character, fx, guides, interactions, materials, pose
from . import layout as L
from . import palette as PAL
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
LOCK_PT = {"palette": "a paleta de cores", "style": "o estilo", "camera": "a câmera e o enquadramento",
           "lights": "a iluminação", "guides": "as proporções", "atmosphere": "a atmosfera", "background": "o fundo",
           "materials": "os materiais e texturas"}
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


EXTRA_FNS = {"character": character.sentence, "pose": pose.sentence, "material": materials.entity_sentence, "wind": fx.wind_sentence}


def entity_extras(scene: Scene, entity_id: str, skip: frozenset = frozenset()) -> list[str]:
    """Frases de camadas (personagem, pose, material, vento) de uma entidade; vazio quando não há. `skip` poda camadas."""
    return [t for t in (fn(scene, entity_id) for k, fn in EXTRA_FNS.items() if k not in skip) if t]


def entity_sentence(scene: Scene, e: Entity, skip: frozenset = frozenset()) -> str:
    where = P.entity_position(e, scene.grid_kind)
    sep = ", " if where.startswith("com ") else " "
    parts = [f"{P.cap(e.label)}{sep}{where}: {e.desc}."]
    if e.orient:
        parts.append(f"Orientação: {V.DIRECTION_PT[e.orient]} ({P.SCREEN_NOTE}).")
    if e.brightness == "max":
        parts.append("É o elemento mais brilhante e mais saturado da imagem.")
    elif e.brightness == "low" or e.saturation == "muted":
        parts.append("Permanece discreto: baixa saturação e brilho contido.")
    if "details" not in skip:
        parts.extend(f"{d}." if not d.endswith(".") else d for d in e.details)
    for extra in entity_extras(scene, e.id, skip):
        if extra:
            parts.append(extra)
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
    extra = PAL.sentence(scene.data)
    if extra:
        bits.append(extra)
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


def build_ir(scene: Scene, passname: str | None = None, skip: frozenset = frozenset()) -> dict:
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
    for key, text in guides.sections(scene).items():
        ir[key] = text
    intent = d["intent"]
    if intent.get("emotion") or intent.get("story"):
        ir["intencao"] = " ".join(
            x for x in (
                f"Emoção: {intent['emotion']}." if intent.get("emotion") else "",
                f"História: {intent['story']}." if intent.get("story") else "",
            ) if x
        )
    focal_ent = scene.focal_target().entity
    ir["planos"] = {
        plane: [entity_sentence(scene, e, frozenset() if focal_ent is e else skip) for e in scene.entities if e.plane == plane]
        for plane in PLANE_ORDER
        if any(e.plane == plane for e in scene.entities)
    }
    inter = interactions.sentences(scene)
    if inter:
        ir["interacoes"] = inter
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
    atm = fx.atmosphere_section(scene)
    if atm:
        ir["atmosfera"] = atm
    det = materials.detail_section(scene)
    if det:
        ir["detalhe_de_textura"] = det
    bg = fx.background_section(scene, passname)
    if bg:
        ir["fundo"] = bg
    if d.get("lock"):
        names = [scene.by_id[n].label if n in scene.by_id else LOCK_PT.get(n, n) for n in d["lock"]]
        ir["manter_igual"] = "Mantenha exatamente igual à versão anterior: " + "; ".join(names) + "."
    if d.get("finish"):
        ir["acabamento"] = d["finish"]
    if d.get("corrections"):
        ir["correcoes"] = [c for c in d["corrections"] if isinstance(c, str) and c.strip()]
    if reminders:
        ir["lembrete_final"] = reminders
    return ir


# ---------------------------------------------------------------------------
def to_prose(scene: Scene, passname: str | None = None) -> str:
    return _prose_from_ir(build_ir(scene, passname))


def _prose_from_ir(ir: dict) -> str:
    head = f"Ilustração: {ir['estilo']}. {ir['quadro']} {ir['grade']}"
    for k in ("pixel", "guias"):
        if k in ir:
            head += " " + ir[k]
    lines = [head, "", "PRIORIDADES (cumpra primeiro):"]
    lines += [f"{i}. {t}" for i, t in enumerate(ir["prioridades"], 1)]
    if "intencao" in ir:
        lines += ["", "INTENÇÃO: " + ir["intencao"]]
    if "atmosfera" in ir:
        lines += ["", "ATMOSFERA: " + ir["atmosfera"]]
    lines += ["", "CENA:"]
    for plane, sentences in ir["planos"].items():
        lines.append(f"{V.PLANE_PT[plane]}:")
        lines += [f"- {s}" for s in sentences]
    if "interacoes" in ir:
        lines += ["", "INTERAÇÕES:"] + [f"- {s}" for s in ir["interacoes"]]
    if "iluminacao" in ir:
        lines += ["", "ILUMINAÇÃO:"] + [f"- {s}" for s in ir["iluminacao"]]
    if "camera" in ir:
        lines += ["", "CÂMERA: " + ir["camera"]]
    if "detalhe_de_textura" in ir:
        lines += ["", "DETALHE E TEXTURA: " + ir["detalhe_de_textura"]]
    if "paleta" in ir:
        lines += ["", "PALETA: " + ir["paleta"]]
    if "ordem_do_olhar" in ir:
        lines += ["", "ORDEM DO OLHAR: " + " → ".join(f"{i}) {t}" for i, t in enumerate(ir["ordem_do_olhar"], 1)) + "."]
    if "detalhes" in ir:
        lines += ["", "DETALHES: " + "; ".join(ir["detalhes"]) + "."]
    if "fundo" in ir:
        lines += ["", "FUNDO: " + ir["fundo"]]
    if "acabamento" in ir:
        lines += ["", "ACABAMENTO: " + ir["acabamento"] + "."]
    if "manter_igual" in ir:
        lines += ["", "TRAVAS: " + ir["manter_igual"]]
    if ir.get("correcoes"):
        lines += ["", "CORREÇÕES DA VERSÃO ANTERIOR (aplique):"] + [f"- {t}" for t in ir["correcoes"]]
    if "lembrete_final" in ir:
        lines += ["", "LEMBRETE FINAL (crítico):"] + [f"- {t}" for t in ir["lembrete_final"]]
    return "\n".join(lines) + "\n"


def to_json(scene: Scene, passname: str | None = None) -> str:
    ir = build_ir(scene, passname)
    out = {"prioridade_maxima": ir["prioridades"]}
    out.update({k: v for k, v in ir.items() if k != "prioridades"})
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def to_regions(scene: Scene, size: str | None = None, passname: str | None = None) -> str:
    w_px, h_px = L.size_px(scene.ratio, size)
    d = scene.data
    ir = build_ir(scene, passname)
    style = d["style"]
    weights = {k: float(v) / 100.0 for k, v in (style.get("mix") or {}).items()}
    global_bits = [ir["estilo"], ir["quadro"], ir["grade"]]
    for key in ("pixel", "guias", "atmosfera", "fundo", "paleta", "camera", "intencao", "interacoes", "iluminacao", "ordem_do_olhar",
                "detalhes", "detalhe_de_textura", "manter_igual", "acabamento", "correcoes", "lembrete_final"):
        if key in ir:
            v = ir[key]
            global_bits.append(" ".join(v) if isinstance(v, list) else v)
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
            "prompt": " ".join([e.desc + (f", orientação {V.DIRECTION_PT[e.orient]} ({P.SCREEN_NOTE})" if e.orient else "")]
                               + entity_extras(scene, e.id)),
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


def to_compact(scene: Scene, passname: str | None = None) -> str:
    return _compact_from_ir(build_ir(scene, passname))


def _compact_from_ir(ir: dict) -> str:
    """Mesmo conteúdo da prosa, sem cabeçalhos, sem numeração e sem o que a prosa repete: menos tokens, com perdas DECLARADAS.

    Fora dela: o bloco PRIORIDADES (as frases dos asserts: a posição de cada entidade segue na própria frase da entidade),
    a ORDEM DO OLHAR e o LEMBRETE FINAL. `scenelang compile --target compact --loss` lista o que isso custa.
    """
    from . import pose as PO

    parts = [ir["estilo"], ir["quadro"], ir["grade"]]
    for key in ("intencao", "atmosfera"):
        if key in ir:
            parts.append(ir[key])
    for plane, sentences in ir["planos"].items():
        parts.append(f"[{plane}] " + " ".join(sentences))
    for key in ("interacoes", "iluminacao", "camera", "detalhe_de_textura", "paleta", "detalhes", "fundo", "acabamento", "manter_igual", "correcoes"):
        if key in ir:
            v = ir[key]
            parts.append(" ".join(v) if isinstance(v, list) else v)
    return " ".join(parts).replace(PO.POSE_HEADER, PO.POSE_HEADER_SHORT) + "\n"


# ---- orçamento de tokens ---------------------------------------------------------------------------------------
# Do que menos pesa para o que mais pesa. Nunca se poda: estilo, quadro, grade, prioridades essenciais, frase-base de cada
# entidade, câmera, fundo, acabamento, travas e correções; a entidade focal mantém todas as camadas.
BUDGET_LADDER = ("detalhe_de_textura", "ordem_do_olhar", "lembrete_final", "detalhes", "entity:wind", "entity:details", "entity:material",
                 "iluminacao", "atmosfera", "entity:pose", "entity:character", "intencao", "paleta", "prioridades")
PRIORITY_KEEP = 6      # no último degrau, ficam o foco, os reforçados e os primeiros asserts até este total


def _render_budget(scene, target, passname, dropped):
    skip = frozenset(k.split(":", 1)[1] for k in dropped if k.startswith("entity:"))
    ir = build_ir(scene, passname, skip)
    for k in dropped:
        if not k.startswith("entity:") and k != "prioridades":
            ir.pop(k, None)
    if "prioridades" in dropped:
        boost, _ = _ordered_asserts(scene)
        keep = max(PRIORITY_KEEP, 1 + len(boost))
        ir["prioridades"] = ir["prioridades"][:keep]
    return (_prose_from_ir if target == "prose" else _compact_from_ir)(ir)


def compile_budget(scene: Scene, target: str = "prose", tokens: int = 250, passname: str | None = None) -> dict:
    """Compila `prose`/`compact` dentro de um orçamento de tokens, podando degrau a degrau o que menos pesa.

    Devolve {text, tokens, method, budget, fits, dropped}. `dropped` lista o que saiu (para o relatório de perdas); se mesmo
    assim estourar, `fits` é False e o texto é o mínimo possível — nada essencial é cortado só para caber."""
    from .bench import count_tokens

    if target not in ("prose", "compact"):
        raise ValueError("--token-budget só vale para os destinos prose e compact")
    dropped: list[str] = []
    text = _render_budget(scene, target, passname, dropped)
    info = count_tokens(text)
    for step in BUDGET_LADDER:
        if info["tokens"] <= tokens:
            break
        dropped.append(step)
        text = _render_budget(scene, target, passname, dropped)
        info = count_tokens(text)
    return {"text": text, "tokens": info["tokens"], "method": info["method"], "budget": tokens, "fits": info["tokens"] <= tokens, "dropped": dropped}


BACKENDS = {"prose": to_prose, "json": to_json, "regions": to_regions, "compact": to_compact}


def delta_prompt(old: Scene, new: Scene) -> str:
    """Prompt de EDIÇÃO: só o que mudou da cena anterior para a nova, para quem aceita continuar de uma imagem existente.

    Precisa da imagem anterior como entrada; sem ela, use o prompt completo. Entidades iguais entram só como «mantenha»;
    entidades novas ou alteradas entram com a frase inteira; seções globais alteradas entram com o texto novo. Devolve ""
    quando nada mudou. Cenas com `lock` já têm «manter igual» próprio, que segue valendo.
    """
    from . import deps

    dl = deps.delta(old.data, new.data)
    if dl.empty:
        return ""
    lines: list[str] = []
    ir_old, ir_new = build_ir(old), build_ir(new)
    keep = [new.by_id[i].label for i in dl.unchanged if i in new.by_id]
    if keep:
        lines.append("Mantenha exatamente igual à imagem anterior, sem alterar posição, forma nem cor: " + "; ".join(keep) + ".")
    if dl.removed:
        lines.append("Remova: " + "; ".join(old.by_id[i].label for i in dl.removed if i in old.by_id) + ".")
    for i in dl.changed + dl.added:
        e = new.by_id[i]
        lines.append(("Altere" if i in dl.changed else "Acrescente") + f" {e.label}: " + entity_sentence(new, e))
    if dl.reordered:
        lines.append("A ordem de sobreposição dos elementos mudou: " + "; ".join(new.by_id[i].label for i in [e.id for e in new.entities]) + ".")
    skip = {"planos", "prioridades", "manter_igual"}
    for k, v in ir_new.items():
        if k not in skip and ir_old.get(k) != v:
            lines.append((" ".join(v) if isinstance(v, list) else str(v)))
    return "\n".join(lines) + "\n"
