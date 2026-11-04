"""Relatório de perdas: o que a cena declara e o backend escolhido não leva ao gerador (ou leva só aproximado).

Nada some em silêncio: `scenelang compile --loss` lista; `--strict` falha quando há perda real.

níveis:
- lost: a informação existe na cena e NÃO chega ao prompt;
- approx: chega com menos precisão (caixa → região por palavras);
- unchecked: declarado, mas só pode ser conferido na imagem pronta (asserts/verify) ou falta declarar.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import vocab as V

_KNOWN_PT = {v.split(" ", 1)[1] for v in V.PART_PT.values()}


@dataclass
class Loss:
    level: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.path}: {self.message}"


def _part_names(e: dict):
    wp = e.get("wind_parts")
    if isinstance(wp, dict):
        yield from (("wind_parts", k) for k in wp)
    elif isinstance(wp, list):
        yield from (("wind_parts", k) for k in wp if isinstance(k, str))
    m = e.get("material")
    if isinstance(m, dict) and isinstance(m.get("parts"), dict):
        yield from (("material.parts", k) for k in m["parts"])


def report(scene, backend: str = "prose") -> list[Loss]:
    d = scene.data
    out: list[Loss] = []
    for i, e in enumerate(d.get("entities") or []):
        if not isinstance(e, dict):
            continue
        own = set((e.get("parts") or {}) if isinstance(e.get("parts"), dict) else ())
        for where, name in _part_names(e):
            if name not in V.PART_PT and name not in _KNOWN_PT and name not in own:
                out.append(Loss("lost", f"$.entities[{i}].{where}",
                                f"a parte {name!r} não tem tradução e entra crua no prompt em português; "
                                "use um nome conhecido (scenelang vocab) ou descreva-a em `parts`"))
    if backend in ("prose", "json"):
        boxed = [e["id"] for e in d.get("entities") or [] if isinstance(e, dict) and "box" in e]
        if boxed:
            out.append(Loss("approx", "$.entities[*].box",
                            "a caixa vira palavra de região (ex.: 'região central esquerda'); tamanho e posição exata não chegam ao gerador: "
                            + ", ".join(boxed)))
    if not d.get("asserts"):
        out.append(Loss("unchecked", "$.asserts", "sem asserts: nada impede que o gerador espelhe ou troque a composição sem ser detectado"))
    if d.get("verify"):
        out.append(Loss("unchecked", "$.verify", "as verificações de imagem só rodam depois da geração (scenelang verify)"))
    if d.get("asserts") and backend != "regions":
        out.append(Loss("unchecked", "$.asserts", "asserts de layout valem para o esquema (scenelang check); o gerador pode não obedecê-los: "
                        "confira na imagem"))
    return out


def blocking(items: list[Loss]) -> list[Loss]:
    """Perdas que falham no modo estrito: informação que sumiria ou cena sem como conferir."""
    return [x for x in items if x.level == "lost" or (x.level == "unchecked" and x.path == "$.asserts" and "sem asserts" in x.message)]
