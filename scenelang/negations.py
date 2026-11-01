"""Negações viram afirmações.

Modelos de imagem às vezes desenham o que está citado numa lista de "evitar".
Por isso o compilador nunca repete a negação: troca pela afirmação equivalente.
Frases sem regra geram um aviso pedindo que o autor reescreva de forma afirmativa.
"""
from __future__ import annotations

import re

# (padrão, afirmação, já_coberta). `já_coberta` indica que o compilador sempre
# emite essa ideia nas prioridades; então a negação é aceita, mas não repetida.
NEGATION_RULES: list[tuple[str, str, bool]] = [
    (r"(dois|v[áa]rios|m[úu]ltiplos) pontos focais|pontos focais competindo|foco duplo",
     "um único ponto focal, claro e dominante", True),
    (r"centraliz",
     "composição assimétrica, com o sujeito principal deslocado do centro do quadro", False),
    (r"satura[çc][ãa]o.*fora do (ponto )?foc",
     "saturação contida fora do ponto focal, que concentra a cor mais intensa", False),
    (r"\btexto\b|logotipo|marca d.?[áa]gua|legenda",
     "imagem limpa, formada só pelos elementos da cena", False),
    (r"p[ée]s?.*(cortad|desfocad)|objeto.*(na )?frente",
     "botas e apoio dos pés nítidos, sem objetos na frente deles", False),
    (r"borrad|desfocad",
     "nitidez máxima no ponto focal", False),
]


def to_affirmation(text: str) -> tuple[str, bool] | None:
    """(afirmação, já_coberta) para uma negação conhecida; None se não houver regra."""
    for pattern, affirmation, covered in NEGATION_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return affirmation, covered
    return None
