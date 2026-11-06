"""Histórico de rodadas: contar tentativas por falha, detectar repetição e compactar sem perder evidência.

Cada rodada detalhada: {rodada, imagem, hash_cena, reprovados, aplicadas, adiadas, nao_resolvidas, tags}.
Rodadas antigas viram UM resumo: {resumo: true, rodadas: [a, b], reprovados: {check: n}, aplicadas: {chave: n},
nao_resolvidas: [...], imagens: [...], tags: [...]}. Contagens, primeira/última rodada e imagens ficam; só o detalhe
rodada a rodada é descartado. Entradas antigas (v0.5: só rodada/imagem/reprovados/tags) continuam válidas.
"""
from __future__ import annotations

import copy

MAX_DETAILED = 6        # rodadas detalhadas que ficam na cena
MAX_ATTEMPTS = 3        # tentativas de uma instrução antes de declarar a falha não resolvida pelo prompt


class CorrectionHistory:
    def __init__(self, entries: list | None = None):
        self.entries = [copy.deepcopy(e) for e in (entries or []) if isinstance(e, dict)]

    # -- leitura -----------------------------------------------------------------
    @property
    def next_round(self) -> int:
        n = 0
        for e in self.entries:
            n = max(n, e["rodadas"][1] if e.get("resumo") else int(e.get("rodada", 0) or 0))
        return n + 1

    def failed_count(self, check: str) -> int:
        """Quantas rodadas anteriores reprovaram este check (resumos contam pelo total guardado)."""
        total = 0
        for e in self.entries:
            r = e.get("reprovados") or ([] if e.get("resumo") else [])
            total += int(r.get(check, 0)) if isinstance(r, dict) else int(check in r)
        return total

    def failed_in_last_round(self, check: str) -> bool:
        if not self.entries:
            return False
        last = self.entries[-1]
        r = last.get("reprovados") or []
        return (check in r) if isinstance(r, (list, tuple)) else bool(r.get(check))

    def attempts(self, check: str) -> int:
        """Tentativas consecutivas que não resolveram: zera quando a última rodada não reprovou o check."""
        if not self.failed_in_last_round(check):
            return 0
        n = 0
        for e in reversed(self.entries):
            r = e.get("reprovados") or []
            hit = (check in r) if isinstance(r, (list, tuple)) else bool(r.get(check))
            if not hit:
                break
            n += int(r.get(check, 1)) if isinstance(r, dict) else 1
        return n

    # -- escrita -----------------------------------------------------------------
    def add(self, rodada: int | None, imagem: str, hash_cena: str, plan, failed: list[str], tags: list | None = None) -> dict:
        entry = {"rodada": rodada or self.next_round, "imagem": imagem, "hash_cena": hash_cena, "reprovados": list(dict.fromkeys(failed)),
                 "aplicadas": [c.key for c in plan.applied], "adiadas": [s.failure for s in plan.deferred],
                 "nao_resolvidas": [s.failure for s in plan.unresolved], "tags": list(tags or [])}
        self.entries.append(entry)
        return entry

    def compact(self, keep_last: int = MAX_DETAILED) -> "CorrectionHistory":
        """Resume as rodadas além das `keep_last` mais recentes. Idempotente."""
        detailed = [e for e in self.entries if not e.get("resumo")]
        old = [e for e in self.entries if e.get("resumo")]
        if len(detailed) <= keep_last:
            return self
        cut = len(detailed) - keep_last
        fold, keep = detailed[:cut], detailed[cut:]
        merged = old[0] if old else {"resumo": True, "rodadas": [None, None], "reprovados": {}, "aplicadas": {}, "nao_resolvidas": [],
                                     "imagens": [], "tags": []}
        for extra in old[1:]:
            self._merge(merged, extra)
        for e in fold:
            self._merge(merged, e)
        self.entries = [merged] + keep
        return self

    @staticmethod
    def _merge(m: dict, e: dict) -> None:
        lo, hi = (e["rodadas"] if e.get("resumo") else [e.get("rodada"), e.get("rodada")])
        if lo is not None:
            m["rodadas"][0] = lo if m["rodadas"][0] is None else min(m["rodadas"][0], lo)
            m["rodadas"][1] = hi if m["rodadas"][1] is None else max(m["rodadas"][1], hi)
        for field_ in ("reprovados", "aplicadas"):
            src = e.get(field_) or ([] if not e.get("resumo") else {})
            items = src.items() if isinstance(src, dict) else ((k, 1) for k in src)
            for k, n in items:
                m[field_][k] = m[field_].get(k, 0) + int(n)
        for k in e.get("nao_resolvidas") or []:
            if k not in m["nao_resolvidas"]:
                m["nao_resolvidas"].append(k)
        for img in ([e.get("imagem")] if not e.get("resumo") else e.get("imagens", [])):
            if img and img not in m["imagens"]:
                m["imagens"].append(img)
        for t in e.get("tags") or []:
            if t not in m["tags"]:
                m["tags"].append(t)

    def to_list(self) -> list:
        return copy.deepcopy(self.entries)
