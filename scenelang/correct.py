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
from dataclasses import asdict, dataclass

from . import canon
from . import locate as LC
from . import verify as ver
from .correction import MAX_CORRECTIONS, RULES, CorrectionHistory, Finding, Plan, classify
from .correction import plan as _plan

__all__ = ["Finding", "MAX_CORRECTIONS", "Measurement", "measure_full", "measure", "plan_round", "corrections", "next_scene", "next_scene_plan", "report"]


def _source(items) -> str:
    srcs = {i.source for i in items}
    return next(iter(srcs)) if len(srcs) == 1 else "mista"


@dataclass
class Measurement:
    findings: list
    items: list            # só as entidades `localizada`: sustentam espelhamento e asserts de posição
    located: list          # TODAS as entidades, cada uma com estado, confiança e motivo
    skipped_asserts: list  # asserts de posição que não puderam ser avaliados (faltou medição confiável de alguma entidade)


def _measure_key(scene, image, boxes) -> str:
    import hashlib

    from . import cache as CA

    ih = hashlib.sha256(image.tobytes()).hexdigest()
    # a medição depende da imagem, das caixas informadas e da cena, menos o que nunca a influencia
    data = {k: v for k, v in scene.data.items() if k not in ("history", "corrections", "priority_boost")}
    return CA.key_of(ih, image.size, image.mode, boxes or {}, data)


def measure_full(scene, image, boxes: dict | None = None, use_cache: bool = True) -> Measurement:
    """Roda todas as medições possíveis. `boxes` são caixas {id: [x,y,w,h]} de quem olhou a imagem (null = não aparece).

    Com `use_cache`, a mesma imagem medida de novo contra uma cena equivalente (histórico e correções não contam) devolve o
    resultado guardado — a medição por cor é o passo caro (~1,5 s numa imagem de 1,5 MP). O resultado é compartilhado:
    não o modifique."""
    if use_cache:
        from . import cache as CA

        return CA.DEFAULT.memo("measure", _measure_key(scene, image, boxes), lambda: measure_full(scene, image, boxes, use_cache=False))
    out: list[Finding] = []
    for r in ver.run(scene, image):
        out.append(Finding("verify", r.raw, r.ok, r.detail, "imagem"))
    located = LC.locate_detailed(scene, image, boxes)
    items = LC.usable(located)
    skipped: list = []
    if items:
        src = _source(items)
        conf = min(i.confidence for i in items)
        verdict, detail = LC.mirror_verdict(items)
        if verdict != "incerto":
            out.append(Finding("mirror", "espelhamento", verdict == "ok", f"{verdict} ({detail})", src, conf))
        res, skipped = LC.recheck_asserts(scene, {i.id: i.measured for i in items})
        for r in res:
            out.append(Finding("layout", r.raw, r.ok, r.detail, src, conf))
    return Measurement(out, items, located, skipped)


def measure(scene, image, boxes: dict | None = None) -> tuple[list[Finding], list[LC.Found]]:
    m = measure_full(scene, image, boxes)
    return m.findings, m.items


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


def report(scene, findings: list[Finding], items: list[LC.Found], image_name: str = "", pl: Plan | None = None,
           located: list[LC.Found] | None = None, skipped_asserts: list | None = None) -> dict:
    """Registro estruturado da rodada (dado de avaliação). `hash_cena` é o hash canônico (`canon-v1-sha256`) da cena semântica."""
    hist = CorrectionHistory(scene.data.get("history"))
    pl = pl or _plan(scene, findings, items, hist)
    full = canon.scene_hash(scene.data)
    names = {f.check.split("(")[0] for f in findings if f.kind != "mirror"}
    return {"cena": scene.name, "hash_cena": canon.short(full), "hash_cena_completo": full, "hash_algoritmo": canon.ALGORITHM,
            "rodada": hist.next_round, "imagem": image_name,
            "ok": all(f.ok for f in findings),
            "medicoes": [{**asdict(f), "classe": classify(f)} for f in findings],
            "entidades": [{"id": i.id, "declarada": list(i.declared), "medida": list(i.measured) if i.measured else None, "fonte": i.source,
                           "estado": i.status, "confianca": i.confidence, "motivo": i.reason,
                           "iou": round(LC.iou(i.declared, i.measured), 3) if i.measured else None} for i in (located if located is not None else items)],
            "nao_medidos": {"asserts": list(skipped_asserts or []),
                            "entidades": [{"id": i.id, "estado": i.status, "motivo": i.reason} for i in (located or []) if i.status != LC.LOCALIZADA]},
            "correcoes": [asdict(c) | {"chave": c.key} for c in pl.applied],
            "adiadas": [asdict(s) for s in pl.deferred],
            "nao_resolvidas": [asdict(s) for s in pl.unresolved],
            "cobertura": {"medidos_sem_regra": sorted(n for n in names if not _has_rule(n))},
            "historico_rodadas": hist.next_round - 1}
