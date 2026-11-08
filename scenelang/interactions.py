"""Interações semânticas entre entidades (`interactions:`): COMO duas coisas se relacionam, não só onde estão.

interactions:
  - {from: mage.right_hand, verb: "ergue para golpear", to: hammer}
  - {from: orb, verb: "flutua logo acima de", to: anvil}

`from` e `to` são `entidade` ou `entidade.parte` (a parte é livre: right_hand, head, base…; nomes conhecidos são traduzidos).
`verb` é um texto em português que já traz a preposição. O compilador escreve uma frase ativa por interação; o validador
confere as referências e avisa quando a orientação (`orient`) de quem encara contradiz o lado em que está o alvo.
"""
from __future__ import annotations

import re

from . import layout as L
from . import phrases as P
from . import vocab as V

KEYS = {"from", "verb", "to"}
_REF = re.compile(r"^([a-z][a-z0-9_]*)(?:\.([a-z][a-z0-9_]*))?$")
FACING_VERBS = ("encara", "olha", "fita", "mira", "enfrenta", "ataca", "golpeia", "observa", "encontra", "faces", "looks", "attacks")
PART_EXTRA = {"right_hand": "a mão direita", "left_hand": "a mão esquerda", "right_foot": "o pé direito", "left_foot": "o pé esquerdo",
              "face": "o rosto", "eyes": "os olhos", "hand": "a mão", "hands": "as mãos", "tip": "a ponta", "base": "a base",
              "top": "o topo", "bottom": "a parte de baixo", "front": "a frente", "back": "o dorso", "center": "o centro"}


def split_ref(ref: str) -> tuple[str, str | None]:
    m = _REF.match(str(ref).strip())
    if not m:
        raise ValueError(f"referência malformada: {ref!r} (use entidade ou entidade.parte)")
    return m.group(1), m.group(2)


def part_phrase(part: str) -> str:
    return PART_EXTRA.get(part) or V.PART_PT.get(part) or part.replace("_", " ")


def ref_phrase(scene, ref: str) -> str:
    ent, part = split_ref(ref)
    label = scene.by_id[ent].label
    return label if part is None else f"{part_phrase(part)} {P.de(label)}"


def sentence(scene, item: dict) -> str:
    return f"{P.cap(ref_phrase(scene, item['from']))} {item['verb'].strip()} {ref_phrase(scene, item['to'])}."


def sentences(scene) -> list[str]:
    out = []
    for it in scene.data.get("interactions") or []:
        try:
            out.append(sentence(scene, it))
        except (KeyError, ValueError):
            continue
    return out


def check(c, data: dict, scene) -> None:
    """Valida o formato e as referências; avisa contradição entre `orient` e o lado do alvo."""
    items = data.get("interactions")
    if items is None:
        return
    if not isinstance(items, list) or not items:
        c.error("$.interactions", "deve ser uma lista não vazia de {from, verb, to}", got=items)
        return
    for i, it in enumerate(items):
        p = f"$.interactions[{i}]"
        if not isinstance(it, dict):
            c.error(p, "cada interação deve ser um mapa {from, verb, to}", got=it)
            continue
        for k in it:
            if k not in KEYS:
                c.error(f"{p}.{k}", "campo desconhecido", got=k, accepted=sorted(KEYS))
        ok = True
        for k in ("from", "to"):
            if k not in it:
                c.error(f"{p}.{k}", "campo obrigatório ausente")
                ok = False
                continue
            try:
                ent, _part = split_ref(it[k])
            except ValueError as e:
                c.error(f"{p}.{k}", str(e), got=it[k])
                ok = False
                continue
            if scene is not None and ent not in scene.by_id and ent not in c.skipped:
                c.error(f"{p}.{k}", f"referência a algo que não existe: {ent!r}", got=it[k], accepted=sorted(scene.by_id))
                ok = False
        if not isinstance(it.get("verb"), str) or not it.get("verb", "").strip():
            c.error(f"{p}.verb", "campo obrigatório: texto com o verbo (e a preposição)", got=it.get("verb"))
            ok = False
        if ok and scene is not None:
            _orient_warning(c, p, it, scene)


def _orient_warning(c, p: str, it: dict, scene) -> None:
    verb = it["verb"].strip().lower()
    if not verb.startswith(FACING_VERBS):
        return
    a, b = scene.by_id.get(split_ref(it["from"])[0]), scene.by_id.get(split_ref(it["to"])[0])
    if a is None or b is None or a is b or not a.orient:
        return
    dx = V.DIRECTIONS[a.orient][0]
    gap = L.box_center(b.box)[0] - L.box_center(a.box)[0]
    if dx != 0 and abs(gap) > 0.1 and (dx > 0) != (gap > 0):
        side = "direita" if gap > 0 else "esquerda"
        c.warn(f"{p}.from", f"{a.id} {it['verb'].strip()} {b.id}, que está à {side}, mas `orient: {a.orient}` aponta para o lado oposto",
               got=a.orient, hint=f"use orient para {'right' if gap > 0 else 'left'} ou ajuste as caixas")
