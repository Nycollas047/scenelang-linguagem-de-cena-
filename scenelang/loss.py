"""Relatório de perdas: o que a cena declara e o backend escolhido não leva ao gerador (ou leva só aproximado).

Nada some em silêncio: `scenelang compile --loss` lista; `--strict` falha quando há perda real.

níveis (do pior para o melhor):
- lost: a informação existe na cena e NÃO chega ao prompt (descartada);
- unsupported: a chave existe na cena mas este destino não tem como levá-la (ou ninguém declarou o destino dela);
- approx: chega com menos precisão (caixa → região por palavras, graus → frase);
- external: chega ao prompt, mas só vira resultado com intervenção fora do prompt (pós-processamento, guia em imagem, leitor externo);
- unchecked: declarado, mas só pode ser conferido na imagem pronta (asserts/verify) ou falta declarar;
- preserved: chega ao prompt com o conteúdo declarado (o gerador pode não obedecer: isso é medido depois, não é perda);
- meta: informação de controle que, por projeto, não vai ao gerador (nome da cena, histórico, assinatura de cor).

`fidelity()` só diz "completa" quando não há lost, unsupported, approx, external nem unchecked: a saída nunca promete mais do que preserva.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import vocab as V

_KNOWN_PT = {v.split(" ", 1)[-1] for v in V.PART_PT.values()}


LEVELS = ("lost", "unsupported", "approx", "external", "unchecked", "preserved", "meta")

# Destino de cada chave da cena em cada destino de compilação: chave -> (nível, nota). `*` vale para todos os destinos;
# uma entrada ("regions", chave) tem prioridade. Toda chave aceita pelo validador PRECISA estar aqui (há teste), para uma
# chave nova nunca ficar sem destino declarado.
_ALL = "*"
ALIAS = {"compact": "prose"}      # um backend sem regra própria para a chave herda a do backend de origem
FATE: dict[tuple[str, str], tuple[str, str]] = {}


def _fate(level: str, note: str, *keys: str, backend: str = _ALL) -> None:
    for k in keys:
        FATE[(backend, k)] = (level, note)


_fate("meta", "nome/versão da cena: controle, não vai ao gerador", "scene", "version", "extends", "import", "glossary")
_fate("meta", "registro de rodadas: controle, não vai ao gerador", "history")
_fate("preserved", "vira texto do prompt", "canvas", "grid", "style", "intent", "camera", "lights", "gaze", "details", "finish", "atmosphere",
      "background", "materials", "detail", "lock", "corrections", "priority_boost", "colors", "entities")
_fate("approx", "linhas-guia viram frases; a geometria exata não chega", "guides")
_fate("approx", "pedidos negativos viram afirmações equivalentes; a forma original não chega", "avoid")
_fate("approx", "a paleta chega como nomes/hex no texto; o gerador não é obrigado a usar só essas cores", "palette")
_fate("unchecked", "só confere na imagem pronta (scenelang check / locate)", "asserts")
_fate("unchecked", "só confere na imagem pronta (scenelang verify)", "verify")
# por entidade ("entities.<chave>")
_fate("meta", "identificador: usado nas referências e nas medições, não vai ao gerador", "entities.id")
_fate("meta", "cor(es) usadas só para medir a imagem (locate)", "entities.signature")
_fate("preserved", "vira texto do prompt", "entities.kind", "entities.label", "entities.desc", "entities.plane", "entities.tags", "entities.details",
      "entities.brightness", "entities.saturation", "entities.material", "entities.parts", "entities.wind_parts", "entities.translucent",
      "entities.character", "entities.detail", "entities.orient")
_fate("approx", "a posição vira palavra de região; tamanho e posição exata não chegam", "entities.at", "entities.size", "entities.box", backend="prose")
_fate("approx", "a posição vira palavra de região; tamanho e posição exata não chegam", "entities.at", "entities.size", "entities.box", backend="json")
_fate("preserved", "a caixa vai em box_norm e box_px para quem consome regiões", "entities.at", "entities.size", "entities.box", backend="regions")
_fate("approx", "graus viram frase (ex.: «cotovelo dobrado a 90°»); o gerador não mede ângulo", "entities.pose")


# o destino `compact` descarta de propósito estes blocos da prosa
_fate("lost", "a ordem do olhar não vai no destino compact", "gaze", backend="compact")
_fate("approx", "o reforço em frases dos asserts não vai; a posição segue só na frase de cada entidade", "asserts", backend="compact")


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
    out += _fates(d, backend)
    if not d.get("asserts"):
        out.append(Loss("unchecked", "$.asserts", "sem asserts: nada impede que o gerador espelhe ou troque a composição sem ser detectado"))
    return out


def _fates(d: dict, backend: str) -> list[Loss]:
    """Uma linha por chave presente na cena, com o destino dela neste backend. Chave sem destino declarado → unsupported."""
    out: list[Loss] = []

    def look(key: str, path: str, present: bool):
        if not present:
            return
        level, note = FATE.get((backend, key)) or FATE.get((ALIAS.get(backend), key)) or FATE.get((_ALL, key)) or ("unsupported", "chave sem destino declarado neste backend: não chega ao gerador")
        out.append(Loss(level, path, note))

    for k in d:
        look(k, f"$.{k}", True)
    ents = [e for e in d.get("entities") or [] if isinstance(e, dict)]
    for k in sorted({k for e in ents for k in e}):
        users = [e.get("id", "?") for e in ents if k in e]
        look(f"entities.{k}", f"$.entities[*].{k}", True)
        out[-1].message += f" ({', '.join(map(str, users[:6]))}{'…' if len(users) > 6 else ''})"
    pal = d.get("palette") or {}
    if isinstance(pal, dict) and pal.get("colors") and not any(str(v).startswith("palette_match") for v in d.get("verify") or []):
        out.append(Loss("external", "$.palette.colors", "cores exatas só se garantem depois: `verify: palette_match(...)` mede e `scenelang snap --to-palette` conserta"))
    cv = d.get("canvas") or {}
    if isinstance(cv, dict) and cv.get("pixel_grid"):
        out.append(Loss("external", "$.canvas.pixel_grid", "grade de pixels: geradores costumam ignorá-la; `verify: grid_aligned` mede e `scenelang snap` conserta"))
    if (d.get("background") or {}).get("mode") == "chromakey" if isinstance(d.get("background"), dict) else False:
        out.append(Loss("external", "$.background", "fundo de chroma key: o recorte e a limpeza do vazamento são feitos depois (`scenelang cutout`)"))
    if any(isinstance(e.get("pose"), dict) for e in ents):
        out.append(Loss("external", "$.entities[*].pose", "a pose só é seguida de perto com o guia em imagem (`scenelang pack`/`pose`); só em texto o gerador aproxima"))
    return out


def fidelity(items: list[Loss]) -> str:
    """'completa' só sem nenhuma perda, aproximação, dependência externa ou item por conferir; 'sem garantia' se algo se perde."""
    levels = {x.level for x in items}
    if levels & {"lost", "unsupported"}:
        return "sem garantia"
    if levels & {"approx", "external", "unchecked"}:
        return "parcial"
    return "completa"


def summary(items: list[Loss]) -> dict[str, int]:
    return {lv: sum(x.level == lv for x in items) for lv in LEVELS if any(x.level == lv for x in items)}


def blocking(items: list[Loss]) -> list[Loss]:
    """Perdas que falham no modo estrito: informação que sumiria ou cena sem como conferir."""
    return [x for x in items if x.level in ("lost", "unsupported") or (x.level == "unchecked" and x.path == "$.asserts" and "sem asserts" in x.message)]
