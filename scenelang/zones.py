"""Zonas de respiro (`safe_zones`): onde NÃO pode haver elementos (logotipo, título, HUD, texto da carta).

safe_zones:
  - id: title_area
    box: [0.05, 0.05, 0.40, 0.18]
    rule: background_only      # background_only: só plano de fundo; empty: nenhum elemento (céu e terreno são tolerados)
    purpose: "espaço limpo e escuro para o logotipo do jogo"

Cada zona vira o assert `clear_zone(id)` (conferido por `check`), um retângulo tracejado no esquema/guia e, na imagem
pronta, o verificador `zone_quiet(id[, max_std])` mede o ruído de luminância dentro dela.
"""
from __future__ import annotations

from . import layout as L
from . import phrases as P

RULES = ("background_only", "empty")
KEYS = {"id", "box", "rule", "purpose"}
OVERLAP_EPS = 1e-4          # área normalizada abaixo da qual a interseção é ruído numérico


def zones(data: dict) -> dict[str, dict]:
    out = {}
    for z in data.get("safe_zones") or []:
        if isinstance(z, dict) and isinstance(z.get("id"), str):
            out[z["id"]] = z
    return out


def overlap(a, b) -> float:
    """Área (normalizada) da interseção de duas caixas (x, y, w, h)."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def forbidden(entity, rule: str) -> bool:
    if rule == "empty":
        return entity.kind not in ("sky", "terrain")
    return entity.plane in ("foreground", "midground") and entity.kind not in ("sky", "terrain")


def offenders(scene, zone: dict) -> list[tuple[str, float]]:
    """[(id da entidade, fração DA ENTIDADE que invade a zona)] das que a regra proíbe."""
    box = tuple(float(v) for v in zone["box"])
    out = []
    for e in scene.entities:
        if not forbidden(e, zone.get("rule", "background_only")):
            continue
        area = overlap(box, e.box)
        if area > OVERLAP_EPS:
            out.append((e.id, area / max(e.box[2] * e.box[3], 1e-9)))
    return out


def phrase(scene, zone: dict) -> str:
    x, y, w, h = (float(v) for v in zone["box"])
    pos = P.region_in(L.region_of(scene.grid_kind, x + w / 2, y + h / 2))
    forb = "nenhum personagem, objeto ou estrutura" if zone.get("rule") == "empty" else "nenhum elemento de primeiro plano ou de plano médio"
    txt = (f"O retângulo {pos} (de {x * 100:.0f}% a {(x + w) * 100:.0f}% da largura e de {y * 100:.0f}% a {(y + h) * 100:.0f}% da altura) "
           f"fica livre: {forb} entra nele")
    if zone.get("purpose"):
        txt += f"; {zone['purpose']}"
    return txt + "."


def check(c, data: dict, scene) -> None:
    items = data.get("safe_zones")
    if items is None:
        return
    if not isinstance(items, list) or not items:
        c.error("$.safe_zones", "deve ser uma lista não vazia de zonas {id, box, rule, purpose}", got=items)
        return
    seen: set[str] = set()
    for i, z in enumerate(items):
        p = f"$.safe_zones[{i}]"
        if not isinstance(z, dict):
            c.error(p, "cada zona deve ser um mapa", got=z)
            continue
        for k in z:
            if k not in KEYS:
                c.error(f"{p}.{k}", "campo desconhecido", got=k, accepted=sorted(KEYS))
        zid = z.get("id")
        if not isinstance(zid, str) or not zid:
            c.error(f"{p}.id", "campo obrigatório: identificador da zona", got=zid)
        else:
            if zid in seen:
                c.error(f"{p}.id", "identificador de zona repetido", got=zid)
            if scene is not None and zid in scene.by_id:
                c.error(f"{p}.id", "o identificador já é de uma entidade", got=zid)
            seen.add(zid)
        b = z.get("box")
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b)):
            c.error(f"{p}.box", "deve ser [x, y, largura, altura] numérico", got=b)
        elif not (b[2] > 0 and b[3] > 0 and b[0] >= 0 and b[1] >= 0 and b[0] + b[2] <= 1.0 + 1e-9 and b[1] + b[3] <= 1.0 + 1e-9):
            c.error(f"{p}.box", "a zona deve caber no quadro (0 a 1) e ter largura e altura positivas", got=b)
        if z.get("rule", "background_only") not in RULES:
            c.error(f"{p}.rule", "regra desconhecida", got=z.get("rule"), accepted=list(RULES))
        if "purpose" in z and not isinstance(z["purpose"], str):
            c.error(f"{p}.purpose", "deve ser um texto", got=z["purpose"])
