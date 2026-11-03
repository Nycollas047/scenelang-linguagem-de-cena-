"""Avisos de contradição: coisas que a cena pede ao mesmo tempo e que não cabem juntas."""
from __future__ import annotations

from . import color as C
from . import guides
from . import palette as PAL


def check(c, data: dict, scene) -> None:
    _palette_vs_descriptions(c, data)
    _symmetry_vs_wind(c, data)
    _margin_vs_subject(c, data, scene)
    _drape_vs_wind(c, data)


def _palette_vs_descriptions(c, data: dict) -> None:
    """A descrição cita uma cor que nenhuma cor da paleta exata lembra: o modelo vai seguir a descrição."""
    pal = data.get("palette") or {}
    if pal.get("mode") == "model_picks" and not pal.get("proposal"):
        return   # o modelo ainda vai escolher as cores: nada a comparar
    exact = list(PAL.all_colors(data).values())
    if len(exact) < 2:
        return
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict):
            continue
        sub = {"entities": [e]}
        for name, rgb in PAL.mentioned_colors(sub).items():
            best = min(C.delta_e(rgb, p) for p in exact)
            if best > 45:
                c.warn(f"$.entities[{i}].desc", f"cita a cor {name!r}, mas nenhuma cor da paleta se parece (ΔE {best:.0f}); o modelo tende a seguir a descrição",
                       hint=f"inclua uma cor {name} na paleta ou troque a cor na descrição")


def _symmetry_vs_wind(c, data: dict) -> None:
    sym = [v for v in data.get("verify") or [] if isinstance(v, str) and v.startswith("symmetric(") and "legs" not in v]
    wind = isinstance(data.get("atmosphere"), dict) and isinstance(data["atmosphere"].get("wind"), dict) \
        and data["atmosphere"]["wind"].get("strength", "normal") != "calm"
    movers = [e.get("id") for e in data.get("entities") or [] if isinstance(e, dict) and e.get("wind_parts")]
    if wind and movers and sym:
        c.warn("$.atmosphere.wind", f"vento em {', '.join(movers)} quebra a simetria medida por verify symmetric",
               hint="meça só as pernas com symmetric(vertical, 0.8, legs) ou use vento calm")


def _drape_vs_wind(c, data: dict) -> None:
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict) or not e.get("wind_parts") or not isinstance(e.get("parts"), dict):
            continue
        moving = set(e["wind_parts"]) if isinstance(e["wind_parts"], (list, dict)) else set()
        for part, ref in e["parts"].items():
            spec = ref if isinstance(ref, dict) else (data.get("materials") or {}).get(ref)
            if part in moving and isinstance(spec, dict) and spec.get("drape") in ("stiff", "structured", "heavy"):
                c.warn(f"$.entities[{i}].parts.{part}.drape", f"{part} reage ao vento, mas o caimento {spec['drape']} descreve peça parada",
                       hint="use drape: flowing ou billowing (o vento vem de atmosphere.wind, não do drape)")


def _margin_vs_subject(c, data: dict, scene) -> None:
    g = data.get("guides")
    canvas = data.get("canvas") or {}
    if scene is None or not isinstance(g, dict) or not g.get("margin") or "pixel_grid" not in canvas:
        return
    cells = guides.pixel_cells(canvas, scene.ratio)
    if not cells:
        return
    x0, y0, w, h = guides.subject_box(scene)
    least = min(x0 * cells[0], y0 * cells[1], (1 - x0 - w) * cells[0], (1 - y0 - h) * cells[1])
    if least < g["margin"] - 1e-6:
        c.warn("$.guides.margin", f"a caixa do sujeito deixa só {least:.1f} célula(s) de margem; o pedido é {g['margin']}",
               hint="encolha a caixa do sujeito ou reduza a margem")
