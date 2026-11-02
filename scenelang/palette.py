"""Camada de cor: cores exatas (RGB/CMYK/HSL), paleta fixa ou escolhida pelo modelo.

palette:
  mode: fixed | model_picks     # model_picks: o modelo escolhe as cores base
  space: rgb | cmyk | hsl       # espaço em que o modelo deve responder a proposta
  count: 5                      # total de cores base (fixas + escolhidas)
  harmony: analogous            # monochromatic | analogous | complementary | triadic | free
  colors: {outline: "#1b1b26", skin: {cmyk: [0,30,45,0]}}   # cores fixas
  constraints: {contrast_min: 4.5, min_distance: 12, max_colors: 16}
  proposal: {main: "#c0392b", ...}   # preenchida pelo modelo (comando plan-apply)
"""
from __future__ import annotations

from . import color as C
from .checks import enum_check, is_num, unknown_keys

MODES = ("fixed", "model_picks")
CONSTRAINT_KEYS = {"contrast_min", "min_distance", "max_colors"}
HARMONY_PT = {"monochromatic": "monocromática", "analogous": "análoga", "complementary": "complementar",
              "triadic": "triádica", "free": "livre"}
ROLE_PT = {"outline": "contorno", "skin": "pele", "hair": "cabelo", "main": "cor principal", "accent": "acento",
           "shadow": "sombra", "light": "luz", "background": "fundo", "metal": "metal", "cloth": "tecido"}


def resolve_spec(data: dict, spec, _depth: int = 0):
    """Cor RGB de uma especificação, aceitando referências '@nome' à tabela `colors` da cena."""
    if isinstance(spec, str) and spec.startswith("@"):
        table = data.get("colors") or {}
        name = spec[1:]
        if name not in table or _depth > 5:
            raise C.ColorError(f"cor nomeada inexistente: {spec!r} (disponíveis: {', '.join('@' + k for k in table) or 'nenhuma'})")
        return resolve_spec(data, table[name], _depth + 1)
    return C.parse_color(spec)


def _colors_map(data: dict, raw, tolerant: bool = True) -> dict[str, tuple[int, int, int]]:
    out = {}
    if isinstance(raw, dict):
        for role, spec in raw.items():
            try:
                out[str(role)] = resolve_spec(data, spec)
            except C.ColorError:
                if not tolerant:
                    raise
    return out


def fixed_colors(data: dict) -> dict[str, tuple[int, int, int]]:
    return _colors_map(data, (data.get("palette") or {}).get("colors"))


def proposal_colors(data: dict) -> dict[str, tuple[int, int, int]]:
    return _colors_map(data, (data.get("palette") or {}).get("proposal"))


def all_colors(data: dict) -> dict[str, tuple[int, int, int]]:
    """Cores exatas conhecidas: fixas + proposta do modelo."""
    return {**proposal_colors(data), **fixed_colors(data)}


def approx_named_colors(data: dict) -> dict[str, tuple[int, int, int]]:
    """Cores citadas só por nome (dominant, accent). Aproximadas: servem para avisos, não para medir."""
    pal = data.get("palette") or {}
    out = {}
    names = list(pal.get("dominant") or []) + ([pal["accent"]] if isinstance(pal.get("accent"), str) else [])
    for n in names:
        if isinstance(n, str):
            rgb = C.name_to_rgb(n)
            if rgb:
                out[n] = rgb
    return out


def mentioned_colors(data: dict) -> dict[str, tuple[int, int, int]]:
    """Cores citadas por nome nas descrições das entidades (ex.: 'capa azul'). Aproximadas."""
    import re

    text = " ".join(
        str(x) for e in data.get("entities") or [] if isinstance(e, dict)
        for x in [e.get("label", ""), e.get("desc", ""), *(e.get("details") or [])]
    ).lower()
    return {n: rgb for n, rgb in C.NAMES_PT.items() if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w])", text)}


def reference_colors(data: dict) -> list[tuple[int, int, int]]:
    return (list(all_colors(data).values()) + list(approx_named_colors(data).values())
            + list(mentioned_colors(data).values()))


# ---------------------------------------------------------------------------
def check(c, data: dict) -> None:
    table = data.get("colors")
    if table is not None:
        if not isinstance(table, dict):
            c.error("$.colors", "deve ser um mapa nome → cor", got=table)
        else:
            for name, spec in table.items():
                try:
                    C.parse_color(spec)
                except C.ColorError as e:
                    c.error(f"$.colors.{name}", str(e), got=spec)
    pal = data.get("palette")
    if not isinstance(pal, dict):
        return
    mode = pal.get("mode", "fixed")
    enum_check(c, "$.palette.mode", mode, MODES, required=False)
    if "space" in pal:
        enum_check(c, "$.palette.space", pal["space"], C.SPACES)
    if "harmony" in pal:
        enum_check(c, "$.palette.harmony", pal["harmony"], C.HARMONIES)
    count = pal.get("count")
    if count is not None and not (isinstance(count, int) and not isinstance(count, bool) and 2 <= count <= 12):
        c.error("$.palette.count", "deve ser um inteiro entre 2 e 12", got=count)
        count = None
    cons = pal.get("constraints")
    if cons is not None:
        if not isinstance(cons, dict):
            c.error("$.palette.constraints", "deve ser um mapa", got=cons)
            cons = None
        else:
            unknown_keys(c, "$.palette.constraints", cons, CONSTRAINT_KEYS)
            for k, v in cons.items():
                if k in CONSTRAINT_KEYS and not (is_num(v) and v > 0):
                    c.error(f"$.palette.constraints.{k}", "deve ser um número positivo", got=v)
    for key in ("colors", "proposal"):
        raw = pal.get(key)
        if raw is None:
            continue
        if not isinstance(raw, dict) or not raw:
            c.error(f"$.palette.{key}", "deve ser um mapa papel → cor", got=raw)
            continue
        for role, spec in raw.items():
            try:
                resolve_spec(data, spec)
            except C.ColorError as e:
                c.error(f"$.palette.{key}.{role}", str(e), got=spec)

    fixed, prop = fixed_colors(data), proposal_colors(data)
    if mode == "fixed" and pal.get("proposal"):
        c.warn("$.palette.proposal", "a proposta é ignorada em mode: fixed", hint="use mode: model_picks")
    if mode == "model_picks" and count is not None and len(fixed) > count:
        c.error("$.palette.count", "há mais cores fixas do que o total de cores pedido", got=count)
    if mode == "model_picks" and prop:
        _check_proposal(c, data, pal, fixed, prop, count, cons or {})
    elif mode == "fixed" and fixed and pal.get("harmony"):
        ok, detail = C.check_harmony(list(fixed.values()), pal["harmony"])
        if not ok:
            c.warn("$.palette.harmony", f"as cores fixas não seguem a harmonia {pal['harmony']}: {detail}")


def _check_proposal(c, data, pal, fixed, prop, count, cons) -> None:
    for role, rgb in fixed.items():
        if role in prop and C.delta_e(prop[role], rgb) > 1.0:
            c.error(f"$.palette.proposal.{role}", "a proposta mudou uma cor fixa", got=C.to_hex(prop[role]),
                    hint=f"mantenha {C.to_hex(rgb)}")
    merged = {**prop, **fixed}
    if count is not None and len(merged) != count:
        c.error("$.palette.proposal", f"a paleta completa tem {len(merged)} cores, esperado {count}", got=len(merged))
    colors = list(merged.values())
    if pal.get("harmony"):
        ok, detail = C.check_harmony(colors, pal["harmony"])
        if not ok:
            c.error("$.palette.proposal", f"a proposta não segue a harmonia {pal['harmony']}: {detail}")
    if "contrast_min" in cons and len(colors) >= 2:
        best = max(C.contrast_ratio(a, b) for i, a in enumerate(colors) for b in colors[i + 1:])
        if best < cons["contrast_min"]:
            c.error("$.palette.proposal", f"nenhum par de cores atinge o contraste mínimo {cons['contrast_min']}", got=round(best, 2))
    if "min_distance" in cons:
        names = list(merged)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                d = C.delta_e(merged[a], merged[b])
                if d < cons["min_distance"]:
                    c.error("$.palette.proposal", f"as cores {a!r} e {b!r} são parecidas demais (ΔE {d:.1f} < {cons['min_distance']})")


# ---------------------------------------------------------------------------
def _label(role: str, rgb) -> str:
    """'contorno preto (#1b1b26)' para papéis conhecidos; só a cor para os demais."""
    return f"{ROLE_PT[role]} {C.describe(rgb)}" if role in ROLE_PT else C.describe(rgb)


def sentence(data: dict) -> str | None:
    """Frase de cores exatas para o prompt (ou o pedido de escolha, se o modelo decide)."""
    pal = data.get("palette")
    if not isinstance(pal, dict):
        return None
    mode = pal.get("mode", "fixed")
    fixed, prop = fixed_colors(data), proposal_colors(data)
    bits = []
    if fixed:
        bits.append("cores fixas: " + ", ".join(_label(r, rgb) for r, rgb in fixed.items()))
    if mode == "model_picks":
        if prop:
            extra = {r: v for r, v in prop.items() if r not in fixed}
            bits.append("cores escolhidas: " + ", ".join(_label(r, v) for r, v in extra.items()))
        else:
            n = pal.get("count")
            ask = "escolha " + (f"{n - len(fixed)} cor(es) base além das fixas" if n else "as cores base")
            if pal.get("harmony") and pal["harmony"] != "free":
                ask += f", em harmonia {HARMONY_PT[pal['harmony']]}"
            cons = pal.get("constraints") or {}
            if "contrast_min" in cons:
                ask += f", com contraste mínimo {cons['contrast_min']}:1 entre a mais clara e a mais escura"
            bits.append(ask + "; use só essas cores e variações de brilho delas")
    if (pal.get("constraints") or {}).get("max_colors"):
        bits.append(f"no máximo {int(pal['constraints']['max_colors'])} cores na imagem inteira")
    return "; ".join(bits) if bits else None


def plan_request(data: dict) -> dict | None:
    """Pedido estruturado para o modelo propor a paleta (ver comando `plan`)."""
    pal = data.get("palette")
    if not isinstance(pal, dict) or pal.get("mode") != "model_picks":
        return None
    fixed = fixed_colors(data)
    n = pal.get("count", 5)
    return {
        "responda_em": pal.get("space", "rgb"),
        "formato": {"rgb": "[r, g, b] de 0 a 255", "cmyk": "[c, m, y, k] de 0 a 100", "hsl": "[h 0-360, s 0-100, l 0-100]"}[pal.get("space", "rgb")],
        "total_de_cores": n,
        "cores_fixas_nao_mudar": {r: C.to_hex(v) for r, v in fixed.items()},
        "faltam_escolher": max(n - len(fixed), 0),
        "harmonia": pal.get("harmony", "free"),
        "restricoes": pal.get("constraints", {}),
    }
