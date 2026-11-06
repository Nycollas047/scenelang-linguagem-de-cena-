"""Motor de correção: Finding → regra → instrução, com histórico e planejamento. Veja `correct.py` para o laço completo."""
from .history import MAX_ATTEMPTS, MAX_DETAILED, CorrectionHistory
from .planner import MAX_CORRECTIONS, classify, plan
from .rules import RULES, Rule, register, rule_for
from .types import CONFIDENCE, Correction, Finding, Plan, Skipped

__all__ = ["CONFIDENCE", "Correction", "CorrectionHistory", "Finding", "MAX_ATTEMPTS", "MAX_CORRECTIONS", "MAX_DETAILED", "Plan",
           "RULES", "Rule", "Skipped", "classify", "plan", "register", "rule_for"]
