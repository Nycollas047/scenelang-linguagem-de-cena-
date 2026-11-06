"""Planejador: falhas medidas + histórico + regras → plano da rodada (aplicadas, adiadas, não resolvidas)."""
from __future__ import annotations

from .history import MAX_ATTEMPTS, CorrectionHistory
from .rules import Ctx, rule_for
from .types import Correction, Finding, Plan, Skipped

MAX_CORRECTIONS = 12


def classify(f: Finding) -> str:
    """Classe da falha, só para o relatório: o que a sustenta e quão forte é."""
    if f.kind == "verify":
        return "medida_em_pixels"
    return {"informada": "medida_por_caixa_informada", "assinatura": "medida_por_cor", "mista": "medida_mista"}.get(f.source, "medida")


def plan(scene, findings: list[Finding], items: list, history: CorrectionHistory | None = None,
         max_corrections: int = MAX_CORRECTIONS, max_attempts: int = MAX_ATTEMPTS) -> Plan:
    history = history or CorrectionHistory()
    ctx = Ctx(scene, items)
    out = Plan()
    seen = set()
    for f in (x for x in findings if not x.ok):
        rule = rule_for(f)
        if rule is None:
            out.unresolved.append(Skipped(f.check, "sem regra de correção para esta falha: nada foi inventado",
                                          "corrija na cena ou à mão; para uma nova regra, registre uma `Rule`", f.detail))
            continue
        attempt = history.attempts(f.check)
        if attempt >= max_attempts:
            out.unresolved.append(Skipped(f.check, f"a instrução já foi aplicada em {attempt} rodada(s) e a falha persiste",
                                          rule.post_fix or "o prompt não basta: tente outro gerador ou ajuste a cena", f.detail, attempt))
            continue
        if f.confidence < rule.min_confidence:
            out.deferred.append(Skipped(f.check, f"evidência insuficiente (confiança {f.confidence:.2f} < {rule.min_confidence:.2f}, medida {f.source})",
                                        "confirme com `locate --boxes` (caixas de quem olhou a imagem); não alterei o prompt por causa disto", f.detail, attempt))
            continue
        text = rule.build(ctx, f, attempt)
        if not text:
            out.unresolved.append(Skipped(f.check, "a regra não conseguiu montar a instrução com os dados da cena", "", f.detail, attempt))
            continue
        if attempt > 0 and text == rule.build(ctx, f, attempt - 1):
            out.unresolved.append(Skipped(f.check, "a mesma instrução já falhou e a regra não tem versão mais explícita",
                                          rule.post_fix or "", f.detail, attempt))
            continue
        if text in seen:
            continue
        seen.add(text)
        out.applied.append(Correction(rule.name, f.check, text, f.detail, f.confidence, rule.priority, attempt, True, rule.post_fix, list(rule.side_effects)))
    out.applied.sort(key=lambda c: (c.priority, c.failure))
    for c in out.applied[max_corrections:]:
        out.deferred.append(Skipped(c.failure, f"limite de {max_corrections} correções por rodada", "entra na próxima rodada se continuar falhando", c.evidence, c.attempt))
    out.applied = out.applied[:max_corrections]
    return out
