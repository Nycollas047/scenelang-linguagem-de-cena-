"""Regras de correção: uma falha medida vira uma instrução afirmativa.

Para acrescentar um tipo de correção, escreva uma subclasse de `Rule` e registre com `@register`; o planejador,
o histórico e o relatório não mudam. Cada regra declara: que falha trata, a prioridade, a confiança mínima da
medição para agir, os efeitos colaterais possíveis e, se existir, o comando que conserta a imagem depois.
`build(ctx, finding, attempt)` devolve o texto; para `attempt > 0` deve devolver um texto DIFERENTE (mais explícito),
senão o planejador entende que a instrução se esgotou e declara a falha não resolvida.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import phrases as P
from ..assertions import parse_assert
from .types import Finding

POSITION_PT = {"above": "acima de", "below": "abaixo de", "left_of": "à esquerda de", "right_of": "à direita de",
               "inside": "dentro de", "near": "perto de"}
OPPOSITE_PT = {"above": "abaixo", "below": "acima", "left_of": "à direita", "right_of": "à esquerda"}

RULES: list["Rule"] = []


def register(cls):
    RULES.append(cls())
    return cls


def rule_for(f: Finding) -> "Rule | None":
    return next((r for r in RULES if r.matches(f)), None)


@dataclass
class Ctx:
    scene: object
    items: list

    def label(self, ref: str) -> str:
        """Rótulo em português de uma entidade, âncora, região ou ponto da grade (nunca um id cru)."""
        e = self.scene.by_id.get(ref.split(".")[0])
        if e is not None and "." not in ref:
            return e.label
        try:
            t = self.scene.resolve(ref)
            if t.kind == "point":
                return P.point_with_percent(self.scene.grid_kind, t.id)
            return P.target_phrase(self.scene, ref)
        except Exception:  # noqa: BLE001 - referência desconhecida: devolve o que há de mais legível
            return e.label if e else ref

    def where(self, ref: str) -> str:
        e = self.scene.by_id.get(ref)
        return P.entity_position(e, self.scene.grid_kind) if e else ""


def _name(check: str) -> str:
    return check.split("(")[0].strip()


def _args(check: str) -> list[str]:
    if "(" not in check:
        return []
    return [a.strip() for a in check[check.index("(") + 1:check.rindex(")")].split(",") if a.strip()]


class Rule:
    name = "regra"
    kind = ""                     # verify | layout | mirror
    checks: tuple = ()            # nomes do verificador/predicado; vazio = qualquer da `kind`
    priority = 50
    min_confidence = 0.6
    post_fix: str | None = None
    side_effects: tuple = ()

    def matches(self, f: Finding) -> bool:
        return f.kind == self.kind and (not self.checks or _name(f.check) in self.checks)

    def build(self, ctx: Ctx, f: Finding, attempt: int) -> str | None:
        raise NotImplementedError


# -- composição ---------------------------------------------------------------------------------------------
@register
class MirrorRule(Rule):
    name, kind, priority = "espelhamento", "mirror", 10
    side_effects = ("pode mudar a direção do olhar e dos gestos dos personagens",)

    def build(self, ctx, f, attempt):
        ents = sorted(ctx.items, key=lambda i: i.declared[0] + i.declared[2] / 2)
        if attempt == 0:
            names = [f"{ctx.label(i.id)} {ctx.where(i.id)}" for i in ents[:3]]
            return ("A composição saiu espelhada na versão anterior; mantenha " + "; ".join(names)
                    + " (esquerda e direita são as da imagem, de quem a vê).")
        order = ", ".join(ctx.label(i.id) for i in ents)
        return f"Da esquerda para a direita do quadro, nesta ordem: {order}. Não inverta a cena horizontalmente."


@register
class PositionRule(Rule):
    name, kind, priority = "posicao", "layout", 20
    checks = tuple(POSITION_PT)
    side_effects = ("mexe na composição de quem está perto",)

    def build(self, ctx, f, attempt):
        a = parse_assert(f.check)
        if len(a.args) < 2:
            return None
        A, B = a.args[0].split(".")[0], a.args[1]
        txt = f"{P.cap(ctx.label(A))} fica {POSITION_PT[a.name]} {ctx.label(B)}"
        if attempt == 0:
            if a.name in OPPOSITE_PT:
                txt += f" (antes ficou {OPPOSITE_PT[a.name]})"
            where = ctx.where(A)
            return txt + (f"; posicione {ctx.label(A)} {where}." if where else ".")
        wa, wb = ctx.where(A), ctx.where(B.split(".")[0])
        return txt + (f": {ctx.label(A)} {wa}, {ctx.label(B)} {wb}." if wa and wb else ", com os dois bem separados no quadro.")


@register
class VisibleRule(Rule):
    name, kind, priority, checks = "visibilidade", "layout", 25, ("visible",)

    def build(self, ctx, f, attempt):
        a = parse_assert(f.check)
        if not a.args:
            return None
        who = ctx.label(a.args[0])
        if attempt == 0:
            return f"{P.cap(who)} aparece inteiro dentro do quadro, sem cortes nas bordas."
        return f"{P.cap(who)} aparece completo, com folga visível entre ele e cada borda do quadro."


GAMEPLAY = ("line_of_sight", "occluded", "no_overlap", "clearance", "connected", "reachable", "no_softlock", "min_paths", "requires")


@register
class GameplayRule(Rule):
    """Predicados de level design reprovados na imagem medida: o texto diz o que reabrir/separar, sem inventar geometria."""

    name, kind, priority, checks = "gameplay", "layout", 24, GAMEPLAY
    side_effects = ("mexe no desenho do mapa: confira a planta depois",)

    def build(self, ctx, f, attempt):
        a = parse_assert(f.check)
        n, g = a.name, a.args
        lab = lambda i: ctx.label(g[i].split(".")[0])  # noqa: E731
        if n == "line_of_sight":
            return (f"Nada bloqueia a visão entre {lab(0)} e {lab(1)}: o espaço entre eles fica aberto, sem parede, pilar nem objeto alto."
                    + ("" if attempt == 0 else " Afaste qualquer cobertura alta da linha reta que liga os dois."))
        if n == "occluded":
            who = f"{lab(2)} fica exatamente entre {lab(0)} e {lab(1)}, bloqueando a visão" if len(g) == 3 else \
                f"{lab(0)} fica escondido da visão de {lab(1)} por um elemento sólido entre eles"
            return who + "." + ("" if attempt == 0 else " O elemento sólido é alto o bastante para cobrir a linha inteira.")
        if n == "no_overlap":
            return f"Os elementos «{g[0]}» e «{g[1]}» ficam separados, cada um no seu espaço, sem sobreposição."
        if n == "clearance":
            return (f"Entre {lab(0)} e {lab(1)} sobra passagem livre de pelo menos {float(g[2]) * 100:.0f}% da altura do quadro."
                    + ("" if attempt == 0 else " Mais espaço vazio entre os dois, de borda a borda."))
        return (f"Mantenha uma passagem contínua e aberta entre {lab(0)} e {lab(1)}: nenhuma parede, abismo ou objeto fecha o caminho."
                + ("" if attempt == 0 else " As portas e pontes que ligam os dois ficam visíveis e desobstruídas."))


@register
class WalkableRule(Rule):
    name, kind, priority, checks = "piso_conectado", "verify", 23, ("walkable_connected",)
    side_effects = ("pode redesenhar paredes e abismos do mapa",)

    def build(self, ctx, f, attempt):
        a = _args(f.check)
        if len(a) < 2:
            return None
        s, g = ctx.label(a[0]), ctx.label(a[1])
        txt = f"Desobstrua a passagem contínua de piso entre {s} e {g}; não feche o corredor com paredes ou abismos."
        return txt if attempt == 0 else txt + f" O mesmo piso liso e claro liga {s} a {g} sem interrupção, com largura de passagem de sobra."


@register
class ClearZoneRule(Rule):
    name, kind, priority, checks = "zona_livre", "layout", 22, ("clear_zone",)
    side_effects = ("tira elementos do canto: a composição pode se deslocar",)

    def build(self, ctx, f, attempt):
        from .. import zones

        a = parse_assert(f.check)
        zone = zones.zones(ctx.scene.data).get(a.args[0]) if a.args else None
        if zone is None:
            return None
        base = zones.phrase(ctx.scene, zone)
        if attempt == 0:
            return base
        return base + " Deixe só fundo liso e escuro nessa área, com os elementos recuados para longe dela."


@register
class ZoneQuietRule(Rule):
    name, kind, priority, checks = "zona_quieta", "verify", 43, ("zone_quiet",)

    def build(self, ctx, f, attempt):
        from .. import zones

        zid = _args(f.check)[0]
        zone = zones.zones(ctx.scene.data).get(zid)
        if zone is None:
            return None
        purpose = f" ({zone['purpose']})" if zone.get("purpose") else ""
        if attempt == 0:
            return f"A zona {zid}{purpose} é uma área lisa, de luminância uniforme, sem textura, detalhe nem ruído."
        return f"Preencha a zona {zid}{purpose} com uma cor quase chapada e sem contraste interno: nenhuma linha, mancha nem brilho dentro dela."


# -- pixel art / paleta -------------------------------------------------------------------------------------
@register
class MaxColorsRule(Rule):
    name, kind, priority, checks = "max_colors", "verify", 30, ("max_colors",)
    post_fix = "scenelang snap CENA IMAGEM --colors N"
    side_effects = ("achata o sombreamento",)

    def build(self, ctx, f, attempt):
        n = _args(f.check)[0]
        if attempt == 0:
            return f"Use no máximo {n} cores na imagem inteira, em áreas chapadas, sem gradiente nem suavização."
        return f"Pinte com exatamente {n} cores ou menos: cada área de uma cor só, sem degradês, sem antialiasing, sem textura de ruído."


@register
class GridAlignedRule(Rule):
    name, kind, priority, checks = "grade", "verify", 31, ("grid_aligned",)
    post_fix = "scenelang snap CENA IMAGEM --grid N"

    def build(self, ctx, f, attempt):
        a = _args(f.check)
        n = a[0] if a else ""
        if not n:
            return None
        if attempt == 0:
            return f"Alinhe cada pixel a uma grade de {n} células de largura; todos os pixels do mesmo tamanho e quadrados, sem meio-pixel."
        return f"Desenhe como um sprite de {n} pixels de largura ampliado sem suavização: blocos quadrados idênticos, bordas nítidas, sem rotação."


@register
class PaletteRule(Rule):
    name, kind, priority, checks = "paleta", "verify", 32, ("palette_match",)
    post_fix = "scenelang snap CENA IMAGEM --to-palette"
    side_effects = ("pode perder detalhes de luz fora da paleta",)

    def build(self, ctx, f, attempt):
        pal = (ctx.scene.data.get("palette") or {}).get("colors") or {}
        hexes = ", ".join(str(v) for v in pal.values() if isinstance(v, str))
        who = _args(f.check)[2:] and ctx.label(_args(f.check)[2])
        if attempt == 0:
            return ("Use somente as cores da paleta" + (f" ({hexes})" if hexes else "") + (f" em {who}" if who else "") + "; não acrescente tons fora dela.")
        return "Pinte cada área com uma cor exata da paleta, sem misturar, sem sombrear com tons fora dela e sem brilho de cor nova."


@register
class SymmetricRule(Rule):
    name, kind, priority, checks = "simetria", "verify", 40, ("symmetric",)
    side_effects = ("enrijece a pose; conflita com `pose` assimétrica declarada",)

    def build(self, ctx, f, attempt):
        legs = "legs" in f.check
        if attempt == 0:
            return "Mantenha as pernas e os pés em posição simétrica em relação ao eixo vertical do corpo." if legs else \
                "Mantenha o sujeito simétrico em relação ao eixo vertical, com os dois lados equivalentes."
        return "Os dois lados do sujeito são espelho um do outro em forma, tamanho e posição" + (", dos quadris para baixo." if legs else ".")


@register
class MarginRule(Rule):
    name, kind, priority, checks = "margem", "verify", 41, ("margin",)
    post_fix = "scenelang snap CENA IMAGEM --fit"

    def build(self, ctx, f, attempt):
        n = _args(f.check)[0]
        if attempt == 0:
            return f"Deixe pelo menos {n} célula(s) de pixel livre entre o sujeito e cada borda do quadro."
        return f"O sujeito fica menor e centralizado, com um respiro de {n} célula(s) de pixel ou mais em todos os lados."


@register
class FitGuidesRule(Rule):
    name, kind, priority, checks = "linhas_guia", "verify", 42, ("fit_guides",)

    def build(self, ctx, f, attempt):
        from .. import guides
        lines = guides.guide_lines(ctx.scene)
        if not lines:
            return None
        parts = []
        if "head_top" in lines:
            parts.append(f"o topo da cabeça a {lines['head_top']:.0%} da altura do quadro")
        if "baseline" in lines:
            parts.append(f"os pés a {lines['baseline']:.0%} da altura")
        ax = guides.axis_x(ctx.scene)
        if ax is not None:
            parts.append(f"o eixo do corpo a {ax:.0%} da largura")
        if not parts:
            return None
        return ("Posicione " + ", ".join(parts) + ("." if attempt == 0 else ", sem deslocar o sujeito dessas linhas."))


# -- fundo de chroma key ------------------------------------------------------------------------------------
@register
class ChromaRule(Rule):
    name, kind, priority, checks = "chroma", "verify", 35, ("chroma_clean",)
    post_fix = "scenelang cutout CENA IMAGEM"

    def build(self, ctx, f, attempt):
        txt = "O fundo é uma cor única e chapada (a cor da chave), sem gradiente, sombra, vinheta, chão nem objetos, até as bordas do quadro."
        return txt if attempt == 0 else txt + " Nenhum elemento do cenário toca as bordas do quadro."


@register
class SpillRule(Rule):
    name, kind, priority, checks = "vazamento", "verify", 36, ("no_spill",)
    post_fix = "scenelang cutout CENA IMAGEM"

    def build(self, ctx, f, attempt):
        txt = "O sujeito não carrega nenhum tom da cor do fundo: sem reflexo, sem contorno e sem luz da cor da chave nas bordas."
        return txt if attempt == 0 else txt + " As bordas do sujeito têm contorno escuro ou neutro, nunca da cor do fundo."
