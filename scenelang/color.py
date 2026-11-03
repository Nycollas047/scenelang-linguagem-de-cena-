"""Cor: formatos (RGB, CMYK, HSL, hex), conversões, distância, contraste e harmonia.

Aviso: a conversão CMYK ↔ RGB aqui é a fórmula ingênua, sem perfil ICC. Serve para
declarar intenção; a cor impressa real depende do perfil de impressão.
"""
from __future__ import annotations

import colorsys
import math
import re

SPACES = ("rgb", "cmyk", "hsl")
HARMONIES = ("monochromatic", "analogous", "complementary", "triadic", "free")
HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class ColorError(ValueError):
    pass


def _nums(v, n, ranges, what):
    """Confere `n` números, cada um dentro do seu intervalo (min, max)."""
    if not (isinstance(v, (list, tuple)) and len(v) == n and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
        raise ColorError(f"{what} espera {n} números")
    rs = ranges if isinstance(ranges, list) else [ranges] * n
    for x, (a, b) in zip(v, rs):
        if not a <= x <= b:
            raise ColorError(f"{what}: valor {x} fora de [{a}, {b}]")
    return [float(x) for x in v]


def parse_color(spec) -> tuple[int, int, int]:
    """Aceita '#rrggbb', {rgb: [r,g,b]}, {cmyk: [c,m,y,k]} (0–100), {hsl: [h,s,l]} (graus, %, %)."""
    if isinstance(spec, str):
        m = HEX.match(spec.strip())
        if not m:
            raise ColorError(f"cor em texto deve ser hexadecimal (#rrggbb): {spec!r}")
        h = m.group(1)
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if isinstance(spec, dict) and len(spec) == 1:
        (space, val), = spec.items()
        if space == "hex":
            return parse_color(val)
        if space == "rgb":
            r, g, b = _nums(val, 3, (0, 255), "rgb")
            return round(r), round(g), round(b)
        if space == "cmyk":
            c, m, y, k = _nums(val, 4, (0, 100), "cmyk")
            return cmyk_to_rgb(c, m, y, k)
        if space == "hsl":
            h, s, l = _nums(val, 3, [(0, 360), (0, 100), (0, 100)], "hsl")
            r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
            return round(r * 255), round(g * 255), round(b * 255)
        raise ColorError(f"espaço de cor desconhecido: {space!r} (aceitos: {', '.join(SPACES)}, hex)")
    raise ColorError(f"cor inválida: {spec!r} (use #rrggbb, {{rgb: [...]}}, {{cmyk: [...]}} ou {{hsl: [...]}})")


def cmyk_to_rgb(c, m, y, k) -> tuple[int, int, int]:
    c, m, y, k = (v / 100 for v in (c, m, y, k))
    return tuple(round(255 * (1 - x) * (1 - k)) for x in (c, m, y))  # type: ignore[return-value]


def rgb_to_cmyk(rgb) -> tuple[int, int, int, int]:
    r, g, b = (v / 255 for v in rgb)
    k = 1 - max(r, g, b)
    if k >= 1:
        return 0, 0, 0, 100
    c, m, y = ((1 - x - k) / (1 - k) for x in (r, g, b))
    return tuple(round(v * 100) for v in (c, m, y, k))  # type: ignore[return-value]


def to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def rgb_to_hsl(rgb) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    return h * 360, s * 100, l * 100


def to_lab(rgb) -> tuple[float, float, float]:
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b) -> float:
    """Distância CIE76 entre duas cores RGB (≈2,3 é a menor diferença perceptível)."""
    la, lb = to_lab(a), to_lab(b)
    return math.dist(la, lb)


def luminance(rgb) -> float:
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---- nomes em português (para frases e para ler cores citadas por nome) -----
NAMES_PT: dict[str, tuple[int, int, int]] = {
    "preto": (20, 20, 24), "branco": (245, 245, 240), "cinza": (128, 128, 128), "prata": (192, 196, 204),
    "vermelho": (200, 30, 40), "vinho": (110, 20, 40), "laranja": (240, 130, 30), "amarelo": (245, 215, 50),
    "dourado": (212, 165, 40), "bronze": (160, 110, 50), "marrom": (110, 70, 40), "castanho": (105, 68, 40), "bege": (225, 205, 170),
    "creme": (250, 240, 215), "rosa": (240, 140, 170), "magenta": (220, 30, 150), "roxo": (110, 40, 150),
    "violeta": (140, 90, 200), "lilás": (190, 160, 220), "índigo": (60, 40, 130), "azul-marinho": (20, 35, 90),
    "azul-noite": (20, 30, 80), "azul": (40, 90, 210), "azul-claro": (130, 190, 240), "ciano": (40, 200, 220),
    "turquesa": (30, 190, 180), "verde": (50, 160, 70), "verde-escuro": (20, 80, 45), "verde-limão": (160, 220, 60),
    "verde-oliva": (110, 120, 50), "salmão": (245, 150, 130), "grisalho": (155, 155, 160), "loiro": (225, 190, 110), "ruivo": (170, 75, 35),
    "castanho-escuro": (60, 40, 30), "platinado": (235, 232, 220),
}


def nearest_name(rgb) -> str:
    return min(NAMES_PT, key=lambda n: delta_e(rgb, NAMES_PT[n]))


def name_to_rgb(text: str):
    """Cor de um nome conhecido (ignora maiúsculas), ou None."""
    return NAMES_PT.get(text.strip().lower())


def describe(rgb) -> str:
    return f"{nearest_name(rgb)} ({to_hex(rgb)})"


# ---- harmonia -------------------------------------------------------------
def _chromatic_hues(colors) -> list[float]:
    hues = []
    for c in colors:
        h, s, l = rgb_to_hsl(c)
        if s >= 12 and 15 <= l <= 95 and (max(c) - min(c)) >= 25:   # quase-neutros não têm matiz útil
            hues.append(h)
    return hues


def _span(hues: list[float]) -> float:
    """Menor arco (graus) que cobre todos os matizes."""
    if len(hues) < 2:
        return 0.0
    hs = sorted(hues)
    gaps = [(hs[(i + 1) % len(hs)] - hs[i]) % 360 for i in range(len(hs))]
    return 360 - max(gaps)


def _hue_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _clusters(hues: list[float], width: float = 40) -> list[float]:
    """Agrupa matizes próximos; devolve o matiz médio de cada grupo."""
    groups: list[list[float]] = []
    for h in sorted(hues):
        for g in groups:
            if _hue_gap(h, sum(g) / len(g)) <= width / 2:
                g.append(h)
                break
        else:
            groups.append([h])
    return [sum(g) / len(g) for g in groups]


def check_harmony(colors, kind: str) -> tuple[bool, str]:
    """Confere se os matizes cromáticos da paleta respeitam a harmonia pedida."""
    if kind == "free":
        return True, "harmonia livre"
    hues = _chromatic_hues(colors)
    if len(hues) < 2:
        return True, "paleta quase neutra: sem matizes para comparar"
    span = _span(hues)
    if kind == "monochromatic":
        return span <= 30, f"arco de matiz {span:.0f}° (máximo 30°)"
    if kind == "analogous":
        return span <= 75, f"arco de matiz {span:.0f}° (máximo 75°)"
    cl = _clusters(hues)
    if kind == "complementary":
        ok = len(cl) <= 2 and (len(cl) == 1 or abs(_hue_gap(cl[0], cl[1]) - 180) <= 35)
        return ok, f"{len(cl)} grupo(s) de matiz, esperado 2 opostos (≈180°)"
    if kind == "triadic":
        if len(cl) > 3:
            return False, f"{len(cl)} grupos de matiz, esperado até 3 (≈120° entre si)"
        if len(cl) < 3:
            return True, f"{len(cl)} grupo(s) de matiz (cabe numa tríade)"
        a, b, c = sorted(cl)
        gaps = [b - a, c - b, 360 - (c - a)]
        return all(abs(g - 120) <= 35 for g in gaps), f"separação entre grupos {[round(g) for g in gaps]}° (esperado ≈120°)"
    raise ColorError(f"harmonia desconhecida: {kind!r}")
