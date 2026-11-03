"""Linhas-guia: proporção do personagem, eixo de simetria e grade de pixels.

guides:
  mode: fixed | model_proposes
  subject: warrior | canvas              # de quem são as medidas (padrão: o quadro inteiro)
  canon: stylized | {heads_tall: 4}      # altura do personagem em cabeças
  axis: {symmetry: vertical, x: 0.5}     # x em fração da largura do sujeito
  lines: [head_top, chin, shoulder, waist, knee, baseline]   # ou {waist: 0.52} para ajustar
  margin: 2                              # células vazias nas bordas (exige canvas.pixel_grid)
  proposal: {head_top: 0.1, chin: 0.3, ...}   # y no quadro, preenchida pelo modelo
"""
from __future__ import annotations

from .checks import enum_check, is_num, unknown_keys

CANONS = {"chibi": 2.0, "stylized": 4.0, "child": 5.0, "realistic": 7.5, "heroic": 8.0}
LINE_ORDER = ("head_top", "eye", "chin", "shoulder", "waist", "knee", "baseline")
LINE_PT = {"head_top": "o topo da cabeça", "eye": "a linha dos olhos", "chin": "o queixo", "shoulder": "os ombros",
           "waist": "a cintura", "knee": "os joelhos", "baseline": "a linha do chão (pés)"}
GUIDE_KEYS = {"mode", "subject", "canon", "axis", "lines", "margin", "proposal"}
MODES = ("fixed", "model_proposes")
DEFAULT_LINES = ["head_top", "chin", "shoulder", "waist", "knee", "baseline"]


def heads_of(canon) -> float | None:
    if isinstance(canon, str):
        return CANONS.get(canon)
    if isinstance(canon, dict) and set(canon) == {"heads_tall"} and is_num(canon["heads_tall"]) and 1.5 <= canon["heads_tall"] <= 10:
        return float(canon["heads_tall"])
    if is_num(canon) and 1.5 <= canon <= 10:
        return float(canon)
    return None


def canonical_fractions(heads: float) -> dict[str, float]:
    """Posição de cada linha em fração da altura do sujeito (0 = topo, 1 = pés). Aproximação de estúdio."""
    h = 1.0 / heads
    f = {"head_top": 0.0, "eye": 0.5 * h, "chin": h, "shoulder": 1.25 * h}
    f["waist"] = max(0.55, f["shoulder"] + 0.1)
    f["knee"] = max(0.78, f["waist"] + 0.1)
    f["baseline"] = 1.0
    return f


def pixel_cells(canvas: dict, ratio: float) -> tuple[int, int] | None:
    n = canvas.get("pixel_grid")
    if isinstance(n, int) and not isinstance(n, bool) and 4 <= n <= 512:
        return n, max(1, round(n / ratio))
    return None


# ---------------------------------------------------------------------------
def check(c, data: dict, scene) -> None:
    g = data.get("guides")
    canvas = data.get("canvas") if isinstance(data.get("canvas"), dict) else {}
    if "pixel_grid" in canvas:
        v = canvas["pixel_grid"]
        if not (isinstance(v, int) and not isinstance(v, bool) and 4 <= v <= 512):
            c.error("$.canvas.pixel_grid", "deve ser um inteiro entre 4 e 512 (células na largura)", got=v)
    if g is None:
        return
    if not isinstance(g, dict):
        c.error("$.guides", "deve ser um mapa", got=g)
        return
    unknown_keys(c, "$.guides", g, GUIDE_KEYS)
    mode = g.get("mode", "fixed")
    enum_check(c, "$.guides.mode", mode, MODES, required=False)
    subject = g.get("subject", "canvas")
    if subject != "canvas" and scene is not None and subject not in scene.by_id:
        c.error("$.guides.subject", "entidade inexistente", got=subject, accepted=["canvas"] + sorted(scene.by_id))
    heads = None
    if "canon" in g:
        heads = heads_of(g["canon"])
        if heads is None:
            from .checks import closest, suggest

            near = closest(g["canon"], CANONS) if isinstance(g["canon"], str) else None
            c.error("$.guides.canon", "cânone inválido", got=g["canon"], accepted=sorted(CANONS) + ["{heads_tall: 1.5–10}"],
                    hint=suggest(g["canon"], CANONS) if isinstance(g["canon"], str) else None,
                    fix={"path": "$.guides.canon", "value": near} if near else None)
    if "axis" in g:
        ax = g["axis"]
        if not isinstance(ax, dict):
            c.error("$.guides.axis", "deve ser um mapa", got=ax)
        else:
            unknown_keys(c, "$.guides.axis", ax, {"symmetry", "x"})
            enum_check(c, "$.guides.axis.symmetry", ax.get("symmetry", "vertical"), ("vertical", "none"), required=False)
            if "x" in ax and not (is_num(ax["x"]) and 0 <= ax["x"] <= 1):
                c.error("$.guides.axis.x", "deve ser uma fração entre 0 e 1", got=ax["x"])
    lines = g.get("lines", DEFAULT_LINES)
    overrides: dict = {}
    if isinstance(lines, list):
        for i, n in enumerate(lines):
            enum_check(c, f"$.guides.lines[{i}]", n, LINE_ORDER)
    elif isinstance(lines, dict):
        for n, v in lines.items():
            if enum_check(c, f"$.guides.lines.{n}", n, LINE_ORDER) and not (is_num(v) and 0 <= v <= 1):
                c.error(f"$.guides.lines.{n}", "deve ser uma fração entre 0 e 1", got=v)
        overrides = lines
    else:
        c.error("$.guides.lines", "deve ser uma lista de nomes ou um mapa nome → fração", got=lines)
    if "margin" in g:
        if not (isinstance(g["margin"], int) and not isinstance(g["margin"], bool) and g["margin"] >= 0):
            c.error("$.guides.margin", "deve ser um inteiro ≥ 0 (células)", got=g["margin"])
        elif "pixel_grid" not in canvas:
            c.error("$.guides.margin", "margem em células exige canvas.pixel_grid", got=g["margin"])
    if overrides and heads is not None:
        merged = {**canonical_fractions(heads), **overrides}
        seq = [merged[n] for n in LINE_ORDER if n in merged and (n in overrides or n in DEFAULT_LINES)]
        if any(b <= a for a, b in zip(seq, seq[1:])):
            c.error("$.guides.lines", "as linhas ajustadas saem da ordem (cabeça → pés)", got=overrides)
    prop = g.get("proposal")
    if prop is not None:
        if mode != "model_proposes":
            c.warn("$.guides.proposal", "a proposta é ignorada em mode: fixed", hint="use mode: model_proposes")
        _check_proposal(c, prop, heads)


def _check_proposal(c, prop, heads) -> None:
    if not isinstance(prop, dict) or not prop:
        c.error("$.guides.proposal", "deve ser um mapa linha → y (fração do quadro)", got=prop)
        return
    ys = {}
    for n, v in prop.items():
        if not enum_check(c, f"$.guides.proposal.{n}", n, LINE_ORDER):
            continue
        if not (is_num(v) and 0 <= v <= 1):
            c.error(f"$.guides.proposal.{n}", "deve ser uma fração entre 0 e 1", got=v)
            continue
        ys[n] = float(v)
    seq = [ys[n] for n in LINE_ORDER if n in ys]
    if any(b <= a for a, b in zip(seq, seq[1:])):
        c.error("$.guides.proposal", "as linhas propostas saem da ordem (cabeça → pés)", got=prop)
        return
    if heads and {"head_top", "chin", "baseline"} <= set(ys):
        ratio = (ys["chin"] - ys["head_top"]) / (ys["baseline"] - ys["head_top"])
        if abs(ratio - 1.0 / heads) > 0.04:
            c.error("$.guides.proposal", f"a cabeça mede {ratio:.0%} da altura; o cânone pede {1 / heads:.0%} (±4%)", got=round(ratio, 3))


# ---------------------------------------------------------------------------
def subject_box(scene) -> tuple[float, float, float, float]:
    sub = (scene.data.get("guides") or {}).get("subject", "canvas")
    if sub != "canvas" and sub in scene.by_id:
        return scene.by_id[sub].box
    return (0.0, 0.0, 1.0, 1.0)


def guide_lines(scene) -> dict[str, float]:
    """y de cada linha no quadro (0–1). Usa a proposta do modelo ou o cânone."""
    g = scene.data.get("guides")
    if not isinstance(g, dict):
        return {}
    if g.get("mode") == "model_proposes" and isinstance(g.get("proposal"), dict) and g["proposal"]:
        return {n: float(g["proposal"][n]) for n in LINE_ORDER if n in g["proposal"]}
    heads = heads_of(g.get("canon", "stylized"))
    if heads is None:
        return {}
    fr = canonical_fractions(heads)
    lines = g.get("lines", DEFAULT_LINES)
    if isinstance(lines, dict):
        fr.update({k: float(v) for k, v in lines.items()})
        names = [n for n in LINE_ORDER if n in lines or n in DEFAULT_LINES]
    else:
        names = [n for n in LINE_ORDER if n in lines]
    _, y0, _, h = subject_box(scene)
    return {n: y0 + fr[n] * h for n in names}


def axis_x(scene) -> float | None:
    g = scene.data.get("guides")
    if not isinstance(g, dict):
        return None
    ax = g.get("axis")
    if ax is None or ax.get("symmetry", "vertical") == "none":
        return None
    x0, _, w, _ = subject_box(scene)
    return x0 + float(ax.get("x", 0.5)) * w


# ---------------------------------------------------------------------------
def sections(scene) -> dict[str, str]:
    out: dict[str, str] = {}
    cells = pixel_cells(scene.data["canvas"], scene.ratio)
    if cells:
        out["pixel"] = (f"Pixel art em grade de {cells[0]}×{cells[1]} células: cada célula é um pixel quadrado e nítido, "
                        "sem suavização, sem antialiasing e sem pixels de tamanhos diferentes.")
    g = scene.data.get("guides")
    if not isinstance(g, dict):
        return out
    lines = guide_lines(scene)
    bits = []
    heads = heads_of(g.get("canon", "stylized")) if "canon" in g else None
    if heads:
        bits.append(f"personagem com {heads:g} cabeças de altura (a cabeça mede {100 / heads:.0f}% da altura do corpo)")
    if lines and cells:
        rows = ", ".join(f"{LINE_PT[n]} na linha {min(cells[1], round(y * cells[1]) + (1 if n == 'baseline' else 0))}"
                         for n, y in lines.items())
        bits.append(f"linhas da grade (de 1 a {cells[1]}, contando do topo): {rows}")
    elif lines:
        _, y0, _, h = subject_box(scene)
        pct = ", ".join(f"{LINE_PT[n]} a {round((y - y0) / h * 100)}%" for n, y in lines.items() if n not in ("head_top", "baseline"))
        if pct:
            bits.append("medidas a partir do topo do personagem: " + pct)
    if axis_x(scene) is not None:
        windy = any(isinstance(e, dict) and e.get("wind_parts") for e in scene.data.get("entities", []))
        bits.append("corpo, tronco e pernas simétricos em torno do eixo vertical central"
                    + (" (capa, cabelo e partes leves ao vento ficam de fora da simetria)" if windy else ""))
    if g.get("margin") and cells:
        bits.append(f"margem de {g['margin']} células vazias em volta do personagem")
    if bits:
        out["guias"] = "Proporções: " + "; ".join(bits) + "."
    return out


def svg(scene, px, py, ox: float, W: float, H: float, ink: str = "#0e7490") -> list[str]:
    o: list[str] = []
    cells = pixel_cells(scene.data["canvas"], scene.ratio)
    if cells and cells[0] <= 64:
        for i in range(1, cells[0]):
            o.append(f'<line x1="{px(i / cells[0]):.1f}" y1="{py(0):.1f}" x2="{px(i / cells[0]):.1f}" y2="{py(1):.1f}" stroke="#cbd5e1" stroke-width="0.5"/>')
        for j in range(1, cells[1]):
            o.append(f'<line x1="{px(0):.1f}" y1="{py(j / cells[1]):.1f}" x2="{px(1):.1f}" y2="{py(j / cells[1]):.1f}" stroke="#cbd5e1" stroke-width="0.5"/>')
    for n, y in guide_lines(scene).items():
        o.append(f'<line x1="{px(0):.1f}" y1="{py(y):.1f}" x2="{px(1):.1f}" y2="{py(y):.1f}" stroke="{ink}" stroke-width="1.5" stroke-dasharray="8 4"/>')
        o.append(f'<text x="{px(0) + 6:.1f}" y="{py(y) - 4:.1f}" font-size="10" fill="{ink}">{n}</text>')
    ax = axis_x(scene)
    if ax is not None:
        o.append(f'<line x1="{px(ax):.1f}" y1="{py(0):.1f}" x2="{px(ax):.1f}" y2="{py(1):.1f}" stroke="{ink}" stroke-width="1.5" stroke-dasharray="2 5"/>')
    return o
