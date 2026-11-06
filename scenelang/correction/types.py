"""Tipos do motor de correção: falha medida, instrução corretiva e plano da rodada."""
from __future__ import annotations

from dataclasses import dataclass, field

# confiança da medição por origem: pixels medidos por código > caixa informada por quem olhou > cor de assinatura
CONFIDENCE = {"imagem": 0.95, "informada": 0.9, "assinatura": 0.5}


@dataclass
class Finding:
    kind: str          # verify | layout | mirror
    check: str
    ok: bool
    detail: str
    source: str = ""   # imagem | informada | assinatura | mista
    confidence: float | None = None

    def __post_init__(self):
        if self.confidence is None:
            self.confidence = CONFIDENCE.get(self.source, 0.5 if self.source == "mista" else 0.9)

    @property
    def key(self) -> str:
        return self.check


@dataclass
class Correction:
    """Instrução corretiva afirmativa + o que a sustenta."""
    rule: str
    failure: str                  # check que falhou
    text: str
    evidence: str                 # o que foi medido (detalhe do achado)
    confidence: float
    priority: int                 # menor = aplicada primeiro
    attempt: int                  # 0 = primeira vez que essa falha aparece
    auto_scene: bool = True       # entra sozinha em `corrections` da próxima cena
    post_fix: str | None = None   # comando que conserta a imagem depois da geração, quando existe
    side_effects: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.rule}:{self.failure}"


@dataclass
class Skipped:
    """Falha que não virou instrução: adiada (falta evidência/limite) ou não resolvida (sem regra, ou a regra já falhou)."""
    failure: str
    reason: str
    suggestion: str = ""
    evidence: str = ""
    attempts: int = 0


@dataclass
class Plan:
    applied: list[Correction] = field(default_factory=list)
    deferred: list[Skipped] = field(default_factory=list)
    unresolved: list[Skipped] = field(default_factory=list)

    def texts(self) -> list[str]:
        return [c.text for c in self.applied]
