"""Frases visuais em português: onde números e termos viram linguagem natural.

Tudo que depende do idioma fica neste arquivo, para que outros idiomas possam
ser adicionados depois sem mexer no compilador.
"""
from __future__ import annotations

from . import vocab as V

ROW_PT = {"top": "superior", "mid": "central", "bottom": "inferior"}
COL_PT = {"left": "esquerda", "center": "central", "right": "direita"}
POINT_NOUN = {
    "pt_ul": "o ponto de interesse superior esquerdo da grade",
    "pt_ur": "o ponto de interesse superior direito da grade",
    "pt_ll": "o ponto de interesse inferior esquerdo da grade",
    "pt_lr": "o ponto de interesse inferior direito da grade",
}
OP_WORD = {
    "==": "exatamente",
    ">=": "pelo menos",
    "<=": "no máximo",
    ">": "mais de",
    "<": "menos de",
    "!=": "qualquer quantidade diferente de",
}
SCREEN_NOTE = "do ponto de vista de quem vê a imagem"


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def de(label: str) -> str:
    """Contração de 'de' com o artigo: 'a lança' -> 'da lança'."""
    for art, con in (("as ", "das "), ("os ", "dos "), ("a ", "da "), ("o ", "do ")):
        if label.startswith(art):
            return con + label[len(art):]
    return "de " + label


def em(label: str) -> str:
    """Contração de 'em' com o artigo: 'a lança' -> 'na lança'."""
    for art, con in (("as ", "nas "), ("os ", "nos "), ("a ", "na "), ("o ", "no ")):
        if label.startswith(art):
            return con + label[len(art):]
    return "em " + label


def region_noun(name: str) -> str:
    if name == "mid_center":
        return "o centro do quadro"
    row, col = name.split("_", 1)
    if row == "mid":
        return f"a região central {COL_PT[col]}" if col != "center" else "o centro do quadro"
    if col == "center":
        return f"a região {ROW_PT[row]} central"
    return f"a região {ROW_PT[row]} {COL_PT[col]}"


def region_in(name: str) -> str:
    """'na região superior esquerda' (posição de uma entidade)."""
    noun = region_noun(name)
    return em(noun) if not noun.startswith("o centro") else "no centro do quadro"


def target_phrase(scene, ref: str) -> str:
    """Frase nominal de uma referência: 'a ponta da lança de cristal'."""
    t = scene.resolve(ref)
    if t.kind == "point":
        return POINT_NOUN[t.id]
    if t.kind == "region":
        return region_noun(t.id)
    if t.anchor is None:
        return t.entity.label
    return f"{V.ANCHOR_PT[t.anchor]} {de(t.entity.label)}"


def point_with_percent(grid_kind: str, name: str) -> str:
    """Ponto de interesse com coordenadas em %, para o modelo não confundir com o canto do quadro."""
    from . import layout as L

    x, y = L.point_xy(grid_kind, name)
    return f"{V.POINT_PT[name]} (a cerca de {round(x * 100)}% da esquerda e {round(y * 100)}% do topo, longe da borda)"


def target_position(scene, ref: str) -> str:
    """Frase de posição: 'no ponto de interesse ...' ou 'na região ...'."""
    t = scene.resolve(ref)
    if t.kind == "point":
        return point_with_percent(scene.grid_kind, t.id)
    if t.kind == "region":
        return region_in(t.id)
    return "junto " + de(target_phrase(scene, ref))


def mix_phrase(mix: dict) -> str:
    """Transforma porcentagens de estilo em frases ordenadas por peso."""
    items = sorted(mix.items(), key=lambda kv: -float(kv[1]))
    parts = []
    for i, (name, pct) in enumerate(items):
        pct_txt = f"{float(pct):g}%"
        if i == 0:
            parts.append(
                f"predominantemente {name} ({pct_txt})" if float(pct) >= 60 else f"principalmente {name} ({pct_txt})"
            )
        elif float(pct) >= 40:
            parts.append(f"com forte influência de {name} ({pct_txt})")
        elif float(pct) >= 15:
            parts.append(f"com influência de {name} ({pct_txt})")
        else:
            parts.append(f"com toques de {name} ({pct_txt})")
    return ", ".join(parts)


def position_of_point(grid_kind: str, pt: tuple[float, float], tol: float = 0.03) -> str:
    """Posição de um ponto: o ponto de interesse da grade, se estiver colado nele; senão a região."""
    from . import layout as L

    for name in V.POINT_NAMES:
        gx, gy = L.point_xy(grid_kind, name)
        if abs(pt[0] - gx) <= tol and abs(pt[1] - gy) <= tol:
            return point_with_percent(grid_kind, name)
    return region_in(L.region_of(grid_kind, pt[0], pt[1]))


def entity_position(entity, grid_kind: str) -> str:
    """Onde a entidade está. Objetos orientados são descritos por ponta e base."""
    from . import layout as L

    if entity.orient and V.DIRECTIONS[entity.orient] != (0, 0):
        tip = L.anchor_xy(entity.box, entity.orient, "tip")
        base = L.anchor_xy(entity.box, entity.orient, "base")
        return (
            f"com a ponta {position_of_point(grid_kind, tip)} "
            f"e a base {position_of_point(grid_kind, base)}"
        )
    # grade áurea: centro colado num ponto de interesse (<= 0.06) descreve o próprio ponto, em vez de «no centro»
    return position_of_point(grid_kind, entity.center, tol=0.06 if grid_kind == "golden" else 0.0)


def assert_texts(scene, a) -> tuple[str, str]:
    """(afirmação, pergunta) em português para um assert já interpretado."""
    n, args = a.name, a.args
    tp = lambda i: target_phrase(scene, args[i])  # noqa: E731
    if n in ("above", "below"):
        word = "acima" if n == "above" else "abaixo"
        return (f"{cap(tp(0))} fica {word} {de(tp(1))}.", f"{cap(tp(0))} fica {word} {de(tp(1))}?")
    if n in ("left_of", "right_of"):
        word = "à esquerda" if n == "left_of" else "à direita"
        return (f"{cap(tp(0))} fica {word} {de(tp(1))}.", f"{cap(tp(0))} fica {word} {de(tp(1))}?")
    if n == "inside":
        return (f"{cap(tp(0))} fica dentro {de(tp(1))}.", f"{cap(tp(0))} fica dentro {de(tp(1))}?")
    if n == "near":
        t = scene.resolve(args[1])
        if t.kind == "entity":
            pos = f"junto {de(tp(1))}"
        else:
            pos = target_position(scene, args[1])
        return (f"{cap(tp(0))} fica {pos}.", f"{cap(tp(0))} fica {pos}?")
    if n == "count":
        word = OP_WORD[a.op]
        gloss = scene.data.get("glossary", {}).get(args[0], args[0])
        return (f"Há {word} {a.num} {gloss}.", f"Há {word} {a.num} {gloss}?")
    if n == "visible":
        return (f"Visível por inteiro dentro do quadro: {tp(0)}.", f"{cap(tp(0))} aparece por inteiro dentro do quadro?")
    if n == "facing":
        t = scene.resolve(args[0])
        d = V.DIRECTION_PT[args[1]]
        return (
            f"A orientação {de(t.entity.label)} é {d} ({SCREEN_NOTE}).",
            f"A orientação {de(t.entity.label)} é {d} ({SCREEN_NOTE})?",
        )
    if n == "brightest":
        return (
            f"{cap(tp(0))} é o elemento mais brilhante e mais saturado da imagem.",
            f"{cap(tp(0))} é o elemento mais brilhante e mais saturado da imagem?",
        )
    if n == "clear_zone":
        from . import zones

        txt = zones.phrase(scene, zones.zones(scene.data)[args[0]])
        return (txt, txt.rstrip(".") + "?")
    if n == "focal_single":
        return ("A imagem tem um único ponto focal.", "A imagem tem um único ponto focal, claro e dominante?")
    return (a.raw, a.raw + "?")
