"""Dependências entre entidades, restrições e verificadores, e o que uma edição afeta.

`graph(data)` diz quem referencia quem; `delta(old, new)` diz o que mudou e quais restrições precisam ser reavaliadas.
Isso evita refazer medições e reavaliar `asserts` que a edição não toca, e alimenta o prompt incremental (`delta_prompt`).

Conservador por construção: na dúvida, marca como afetado (reavaliar de mais custa pouco; de menos esconde uma falha).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import canon
from .assertions import parse_assert

# seções cujo texto é descrição livre: não contam como referência a outra entidade
_FREE_TEXT = {"desc", "label", "story", "emotion", "details", "note"}
GEOMETRY_SECTIONS = {"canvas", "grid"}                  # mexer nelas muda a leitura de todas as caixas
VISUAL_SECTIONS = {"style", "palette", "camera", "lights", "atmosphere", "background", "materials", "detail", "finish", "details",
                   "guides", "colors", "avoid"}


def _ids(data: dict) -> list[str]:
    return [str(e["id"]) for e in data.get("entities") or [] if isinstance(e, dict) and "id" in e]


def _refs_in(value, ids: set[str]) -> set[str]:
    """ids citados de forma exata (`id` ou `id.âncora`) em qualquer valor aninhado."""
    out: set[str] = set()
    if isinstance(value, str):
        head = value.split(".")[0] if re.fullmatch(r"[a-z0-9_]+(\.[a-z_]+)?", value) else value
        if head in ids:
            out.add(head)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in _FREE_TEXT:
                out |= _refs_in(v, ids)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out |= _refs_in(v, ids)
    return out


def assert_refs(raw: str, ids: set[str]) -> set[str]:
    try:
        a = parse_assert(raw)
    except Exception:       # assert mal formado: o validador reporta; aqui, sem referências
        return set()
    return {x.split(".")[0] for x in a.args if x.split(".")[0] in ids}


def verify_refs(raw: str, ids: set[str]) -> set[str]:
    """Entidades citadas nos argumentos de um verificador (ex.: o 3º de `palette_match(10, 0.9, sapo)`)."""
    if "(" not in raw:
        return set()
    return {a.strip().split(".")[0] for a in raw[raw.index("(") + 1:raw.rindex(")")].split(",") if a.strip().split(".")[0] in ids}


def graph(data: dict) -> dict:
    ids = set(_ids(data))
    ents = {}
    for e in data.get("entities") or []:
        if isinstance(e, dict) and "id" in e:
            ents[str(e["id"])] = sorted(_refs_in({k: v for k, v in e.items() if k != "id"}, ids) - {str(e["id"])})
    cons = {raw: sorted(assert_refs(raw, ids)) for raw in data.get("asserts") or [] if isinstance(raw, str)}
    other = {sec: sorted(_refs_in(data.get(sec), ids)) for sec in ("gaze", "lights", "intent", "lock", "verify", "guides") if data.get(sec)}
    return {"entities": ents, "asserts": cons, "sections": other}


@dataclass
class Delta:
    changed: list[str] = field(default_factory=list)          # entidades com conteúdo diferente
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    reordered: bool = False
    sections: list[str] = field(default_factory=list)         # seções globais diferentes (style, palette, lights...)
    impacted_asserts: list[str] = field(default_factory=list)
    impacted_verify: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.changed or self.added or self.removed or self.reordered or self.sections)

    @property
    def entities_touched(self) -> list[str]:
        return self.changed + self.added + self.removed


def _by_id(data: dict) -> dict[str, dict]:
    return {str(e["id"]): e for e in data.get("entities") or [] if isinstance(e, dict) and "id" in e}


def delta(old: dict, new: dict) -> Delta:
    """O que mudou da cena `old` para `new` (histórico e correções não contam: não são a cena)."""
    d = Delta()
    o, n = _by_id(old), _by_id(new)
    d.removed = [i for i in o if i not in n]
    d.added = [i for i in n if i not in o]
    for i in n:
        if i in o:
            (d.changed if canon.canonical(o[i]) != canon.canonical(n[i]) else d.unchanged).append(i)
    d.reordered = [i for i in o if i in n] != [i for i in n if i in o]
    keys = (set(old) | set(new)) - {"entities", *canon.TRANSIENT_KEYS}
    d.sections = sorted(k for k in keys if canon.canonical(old.get(k)) != canon.canonical(new.get(k)))
    touched = set(d.entities_touched)
    graph_new, graph_old = graph(new), graph(old)
    # quem aponta para uma entidade tocada também é afetado
    pointing = {i for g in (graph_new, graph_old) for i, refs in g["entities"].items() if touched & set(refs)}
    touched_all = touched | pointing
    geometry = bool(set(d.sections) & GEOMETRY_SECTIONS) or d.reordered
    # união das referências dos dois lados: uma entidade removida só aparece no grafo antigo
    asserts = {raw: set(graph_old["asserts"].get(raw, ())) | set(graph_new["asserts"].get(raw, ()))
               for raw in {*graph_old["asserts"], *graph_new["asserts"]}}
    for raw, refs in asserts.items():
        if geometry or touched_all & refs or raw in (set(old.get("asserts") or []) ^ set(new.get("asserts") or [])):
            d.impacted_asserts.append(raw)
    # verificadores: os de escopo global dependem de qualquer mudança visual; `palette_match(..., entidade)` só da entidade
    visual = bool(touched or d.reordered or set(d.sections) & (VISUAL_SECTIONS | GEOMETRY_SECTIONS))
    for raw in new.get("verify") or []:
        if not isinstance(raw, str):
            continue
        scoped = verify_refs(raw, set(_ids(new)) | set(_ids(old)))
        if (scoped and scoped & touched_all) or (not scoped and visual) or raw in (set(old.get("verify") or []) ^ set(new.get("verify") or [])):
            d.impacted_verify.append(raw)
    return d
