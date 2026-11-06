"""Laço de correção automático: imagem gerada → medições → reforço afirmativo → próxima rodada.

Une as medições que já existem (verify, locate, asserts de posição, espelhamento) e transforma cada falha em
uma instrução afirmativa (o que deve aparecer, e onde estava errado), que a próxima compilação põe no prompt.
Cada rodada deixa um relatório estruturado: é o dado de avaliação (falha medida por código, sem juiz subjetivo).

Responsabilidades (pacote `scenelang.correction`):
- detecção ......... `measure` (aqui) produz `Finding`;
- classificação .... `correction.classify` + confiança por origem da medição;
- instrução ........ `correction.rules` (uma `Rule` por tipo de falha, extensível com `@register`);
- planejamento ..... `correction.plan` (prioridade, limite, adiamento por evidência fraca, esgotamento);
- histórico ........ `correction.CorrectionHistory` (tentativas, repetição, compactação);
- relatório ........ `report` (aqui).
"""
from __future__ import annotations

import copy
from dataclasses import asdict

from . import canon
from . import locate as LC
from . import verify as ver
from .correction import MAX_CORRECTIONS, RULES, CorrectionHistory, Finding, Plan, classify
from .correction import plan as _plan

__all__ = ["Finding", "MAX_CORRECTIONS", "measure", "plan_round", "corrections", "next_scene", "next_scene_plan", "report"]


def _source(items) -> str:
    srcs = {i.source for i in items}
    return next(iter(srcs)) if len(srcs) == 1 else "mista"


def measure(scene, image, boxes: dict | None = None) -> tuple[list[Finding], list[LC.Found]]:
    """Roda todas as medições possíveis. `boxes` são caixas {id: [x,y,w,h]} de quem olhou a imagem."""
    out: list[Finding] = []
    for r in ver.run(scene, image):
        out.append(Finding("verify", r.raw, r.ok, r.detail, "imagem"))
    measured, source = {}, {}
    for k, v in LC.locate_by_signature(scene, image).items():
        measured[k], source[k] = v, "assinatura"
    for k, v in (boxes or {}).items():
        if v is not None and k in scene.by_id:
            measured[k], source[k] = tuple(v), "informada"
    items = LC.compare(scene, measured, source)
    items = [i for i in items if i.source != "assinatura" or LC.reliable(i.declared, i.measured)]
    measured = {i.id: i.measured for i in items}
    if items:
        src = _source(items)
        verdict, detail = LC.mirror_verdict(items)
        if verdict != "incerto":
            out.append(Finding("mirror", "espelhamento", verdict == "ok", f"{verdict} ({detail})", src))
        res, _ = LC.recheck_asserts(scene, measured)
        for r in res:
            out.append(Finding("layout", r.raw, r.ok, r.detail, src))
    return out, items


def plan_round(scene, findings: list[Finding], items: list[LC.Found], history: CorrectionHistory | None = None) -> Plan:
    """Plano da rodada. Sem `history`, usa o que a própria cena já registra."""
    return _plan(scene, findings, items, history or CorrectionHistory(scene.data.get("history")))


def corrections(scene, findings: list[Finding], items: list[LC.Found]) -> list[str]:
    """Uma frase afirmativa por falha com evidência suficiente (compatibilidade: devolve só os textos)."""
    return plan_round(scene, findings, items).texts()


def next_scene(scene, findings, items, image_name: str = "", keep_rounds: int | None = None) -> tuple[dict, list[str]]:
    """Cena da próxima rodada: correções, reforço de prioridade dos asserts reprovados e histórico compactado."""
    new, pl = next_scene_plan(scene, findings, items, image_name, keep_rounds)
    return new, pl.texts()


def next_scene_plan(scene, findings, items, image_name: str = "", keep_rounds: int | None = None) -> tuple[dict, Plan]:
    new = copy.deepcopy(scene.data)
    hist = CorrectionHistory(new.get("history"))
    pl = _plan(scene, findings, items, hist)
    asserts = new.get("asserts", [])
    boost = list(new.get("priority_boost", []))
    for raw in [f.check for f in findings if f.kind == "layout" and not f.ok and f.check in asserts]:
        if raw not in boost:
            boost.append(raw)
    if boost:
        new["priority_boost"] = boost
    new["corrections"] = pl.texts()
    if not new["corrections"]:
        new.pop("corrections")
    hist.add(None, image_name, canon.short(canon.scene_hash(scene.data)), pl, [f.check for f in findings if not f.ok])
    new["history"] = (hist.compact(keep_rounds) if keep_rounds else hist.compact()).to_list()
    return new, pl


def _has_rule(name: str) -> bool:
    return any(name in r.checks or (not r.checks and name == r.kind) for r in RULES)


def report(scene, findings: list[Finding], items: list[LC.Found], image_name: str = "", pl: Plan | None = None) -> dict:
    """Registro estruturado da rodada (dado de avaliação). `hash_cena` é o hash canônico (`canon-v1-sha256`) da cena semântica."""
    hist = CorrectionHistory(scene.data.get("history"))
    pl = pl or _plan(scene, findings, items, hist)
    full = canon.scene_hash(scene.data)
    names = {f.check.split("(")[0] for f in findings if f.kind != "mirror"}
    return {"cena": scene.name, "hash_cena": canon.short(full), "hash_cena_completo": full, "hash_algoritmo": canon.ALGORITHM,
            "rodada": hist.next_round, "imagem": image_name,
            "ok": all(f.ok for f in findings),
            "medicoes": [{**asdict(f), "classe": classify(f)} for f in findings],
            "entidades": [{"id": i.id, "declarada": list(i.declared), "medida": list(i.measured), "fonte": i.source,
                           "iou": round(LC.iou(i.declared, i.measured), 3)} for i in items],
            "correcoes": [asdict(c) | {"chave": c.key} for c in pl.applied],
            "adiadas": [asdict(s) for s in pl.deferred],
            "nao_resolvidas": [asdict(s) for s in pl.unresolved],
            "cobertura": {"medidos_sem_regra": sorted(n for n in names if not _has_rule(n))},
            "historico_rodadas": hist.next_round - 1}
