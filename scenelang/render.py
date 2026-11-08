"""Renderizador de esquema 2D: desenha o layout da cena em SVG (e PNG, se houver rsvg-convert).

Mostra o quadro (retângulo, círculo ou elipse), a grade, as caixas por plano,
setas de orientação, âncoras usadas, o ponto focal, a ordem do olhar e o
resultado de cada assert. É o "ver a cena" de quem não tem gerador de imagem.
"""
from __future__ import annotations

import math
import shutil
import subprocess
from html import escape
from pathlib import Path

from . import guides as G
from . import flow as FL
from . import metrics as MT
from . import topology as TP
from . import zones
from . import skeleton
from . import layout as L
from . import vocab as V
from .assertions import REF_ARGS, evaluate_all, parse_assert
from .model import Scene

PLANE_COLOR = {"background": "#6c7bd6", "midground": "#2fa39a", "foreground": "#d9922b"}
INK, MUTED, FOCAL, GAZE = "#1b1f2a", "#6b7280", "#e5484d", "#8b5cf6"


def _referenced_anchors(scene: Scene) -> set[str]:
    refs: set[str] = set()
    d = scene.data
    refs.add(d["intent"]["focal"])
    refs.update(d.get("gaze", []) or [])
    for raw in d.get("asserts", []) or []:
        a = parse_assert(raw)
        for i in REF_ARGS.get(a.name, ()):
            if i < len(a.args) and "." in a.args[i] and not (a.name == "clearance" and i == 2):   # tolerâncias (0.06) não são âncoras
                refs.add(a.args[i])
    return {r for r in refs if "." in r}


def _floorplan_entity(e, x, y, w, h, col) -> str:
    """Simbologia de planta baixa por etiqueta: paredes duplas, porta com arco (e cadeado), hachura de cobertura, perigo."""
    tags = set(e.tags)
    label = (f'<text x="{x + 6:.1f}" y="{y + 15:.1f}" font-size="11" font-weight="600" fill="{INK}">{escape(e.id)}</text>' if w > 70 else
             f'<text x="{x:.1f}" y="{y - 4:.1f}" font-size="10" font-weight="600" fill="{INK}">{escape(e.id)}</text>')
    if tags & {"room", "corridor"}:
        return (f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#f6f0e2" stroke="{INK}" stroke-width="3"/>'
                f'<rect x="{x + 5:.1f}" y="{y + 5:.1f}" width="{max(w - 10, 1):.1f}" height="{max(h - 10, 1):.1f}" fill="none" stroke="{INK}" stroke-width="1"/>{label}</g>')
    if "door" in tags:
        sw = max(min(w, h), 8)
        arc = f'<path d="M{x:.1f} {y + h:.1f} L{x:.1f} {y + h - sw:.1f} A{sw:.1f} {sw:.1f} 0 0 1 {x + sw:.1f} {y + h:.1f}" fill="none" stroke="{INK}" stroke-width="1.5"/>'
        lock = ""
        if tags & {"locked", "locked_gate"}:
            cx, cy = x + w / 2, y + h / 2
            lock = (f'<rect x="{cx - 5:.1f}" y="{cy - 1:.1f}" width="10" height="8" fill="{INK}"/>'
                    f'<path d="M{cx - 3:.1f} {cy - 1:.1f} v-3 a3 3 0 0 1 6 0 v3" fill="none" stroke="{INK}" stroke-width="1.5"/>')
        return f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#fff" stroke="{INK}" stroke-width="2"/>{arc}{lock}{label}</g>'
    if "cover" in tags:
        pat = "hatch_half" if "half_cover" in tags else "hatch_full"
        return f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="url(#{pat})" stroke="#7c5a2b" stroke-width="2"/>{label}</g>'
    if tags & {"hazard", "trap", "pit"}:
        return (f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#dc2626" fill-opacity="0.18" stroke="#dc2626" stroke-width="2" stroke-dasharray="6 4"/>'
                f'<path d="M{x:.1f} {y:.1f}L{x + w:.1f} {y + h:.1f}M{x + w:.1f} {y:.1f}L{x:.1f} {y + h:.1f}" stroke="#dc2626" stroke-opacity="0.4" stroke-width="1.5"/>{label}</g>')
    return f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="{col}" fill-opacity="0.22" stroke="{col}" stroke-width="2"/>{label}</g>'


def _floorplan_panel(scene, ox, y0, W) -> list[str]:
    """Legenda de escala e mini diagrama do grafo, abaixo do quadro."""
    o: list[str] = []
    n = MT.grid_cells(scene)
    if n:
        cs = MT.cell_size(scene.data)
        bar = W / n * 5
        o.append(f'<text x="{ox}" y="{y0 + 12:.1f}" font-size="11" fill="{MUTED}">escala</text>')
        o.append(f'<rect x="{ox + 50}" y="{y0 + 3:.1f}" width="{bar:.1f}" height="8" fill="{INK}"/>')
        o.append(f'<text x="{ox + 58 + bar:.1f}" y="{y0 + 12:.1f}" font-size="11" fill="{MUTED}">5 células = {5 * cs:g} m (1 célula = {cs:g} m; pixel_grid {n})</text>')
    ids = TP.node_ids(scene.data)
    if not ids:
        return o
    gx, gy, gw, gh = ox + W - 330, y0 + 22, 320.0, 150.0
    o.append(f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" fill="#fff" stroke="#c7ccd6"/>')
    o.append(f'<text x="{gx + 6:.1f}" y="{gy + 14:.1f}" font-size="11" font-weight="700" fill="{INK}">grafo de nós</text>')
    pos = {i: (gx + 20 + scene.by_id[i].center[0] * (gw - 40), gy + 28 + scene.by_id[i].center[1] * (gh - 48)) for i in ids if i in scene.by_id}
    for e in TP.edges(scene.data):
        if e["from"] in pos and e["to"] in pos:
            (x1, y1), (x2, y2) = pos[e["from"]], pos[e["to"]]
            kind = e.get("kind", "bidirectional")
            col = {"locked": "#b45309", "hazard": "#dc2626", "destructible": "#9333ea"}.get(kind, INK)
            dash = EDGE_STYLE.get(kind, "")
            o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="2"'
                     + (f' stroke-dasharray="{dash}"' if dash else "") + (' marker-end="url(#arr)"' if kind == "one_way" else "") + "/>")
            if e.get("via"):
                o.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{(y1 + y2) / 2 - 3:.1f}" font-size="9" fill="{col}">{escape(e["via"])}</text>')
    roles = {n_.get("id"): n_.get("role", "") for n_ in (scene.data.get("graph") or {}).get("nodes", []) if isinstance(n_, dict)}
    for i, (x, y) in pos.items():
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#2fa39a" stroke="{INK}"/>')
        o.append(f'<text x="{x:.1f}" y="{y + 18:.1f}" font-size="9" text-anchor="middle" fill="{INK}">{escape(i)}{" · " + escape(roles[i]) if roles.get(i) else ""}</text>')
    return o


STYLES = ("schematic", "floorplan")
EDGE_STYLE = {"bidirectional": "", "one_way": "", "locked": "6 4", "destructible": "2 4", "hazard": "1 3"}


def render_svg(scene: Scene, width: int = 960, style: str = "schematic") -> str:
    if style not in STYLES:
        raise ValueError(f"estilo de render desconhecido: {style!r} (use {', '.join(STYLES)})")
    plan = style == "floorplan"
    ratio = scene.ratio
    W = float(width)
    H = W / ratio
    ox, oy = 40.0, 64.0
    results = evaluate_all(scene)
    extra_h = 190 if plan else 0           # legenda de escala + mini diagrama do grafo (só na planta baixa)
    panel_h = 28 + 22 * len(results)
    total_w = W + 2 * ox
    total_h = oy + H + 30 + extra_h + panel_h + 24

    def px(x: float) -> float:
        return ox + x * W

    def py(y: float) -> float:
        return oy + y * H

    o: list[str] = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} {total_h:.0f}" width="{total_w:.0f}" height="{total_h:.0f}" font-family="DejaVu Sans, Helvetica, Arial, sans-serif">')
    o.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#1b1f2a"/></marker>')
    o.append('<pattern id="hatch_full" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#7c5a2b" stroke-width="3"/></pattern>')
    o.append('<pattern id="hatch_half" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="9" stroke="#b8893f" stroke-width="2"/></pattern>')
    # forma do quadro como clipPath
    if scene.canvas_shape == "circle":
        r = min(W, H) / 2
        shape = f'<circle cx="{ox + W / 2:.1f}" cy="{oy + H / 2:.1f}" r="{r:.1f}"'
    elif scene.canvas_shape == "ellipse":
        shape = f'<ellipse cx="{ox + W / 2:.1f}" cy="{oy + H / 2:.1f}" rx="{W / 2:.1f}" ry="{H / 2:.1f}"'
    else:
        shape = f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{W:.1f}" height="{H:.1f}"'
    o.append(f'<clipPath id="frame">{shape}/></clipPath></defs>')
    o.append(f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="#f4f5f8"/>')
    o.append(f'<text x="{ox}" y="34" font-size="20" font-weight="700" fill="{INK}">{escape(scene.name)}</text>')
    o.append(f'<text x="{ox}" y="54" font-size="12" fill="{MUTED}">esquema 2D · {escape(scene.data["canvas"]["ratio"])} · {scene.canvas_shape} · grade {escape(scene.grid_kind)}</text>')
    # fundo do quadro
    o.append(f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{W:.1f}" height="{H:.1f}" fill="#dfe2ea"/>')
    o.append(f'{shape} fill="#ffffff"/>')

    # grade (cortada no formato do quadro)
    lines = L.grid_lines(scene.grid_kind)
    o.append('<g clip-path="url(#frame)" stroke="#9aa3b2" stroke-width="1" stroke-dasharray="5 5">')
    for v in lines[1:3]:
        o.append(f'<line x1="{px(v):.1f}" y1="{oy:.1f}" x2="{px(v):.1f}" y2="{oy + H:.1f}"/>')
        o.append(f'<line x1="{ox:.1f}" y1="{py(v):.1f}" x2="{ox + W:.1f}" y2="{py(v):.1f}"/>')
    o.append('</g>')
    for name in V.POINT_NAMES:
        x, y = L.point_xy(scene.grid_kind, name)
        o.append(f'<path d="M{px(x) - 5:.1f} {py(y):.1f}H{px(x) + 5:.1f}M{px(x):.1f} {py(y) - 5:.1f}V{py(y) + 5:.1f}" stroke="#9aa3b2" stroke-width="1.5"/>')

    o.append('<g clip-path="url(#frame)">')
    o.extend(G.svg(scene, px, py, ox, W, H))
    o.append('</g>')

    # zonas de respiro (safe_zones)
    for zid, z in zones.zones(scene.data).items():
        zx, zy, zw, zh = (float(v) for v in z["box"])
        bad = bool(zones.offenders(scene, z))
        col = "#b91c1c" if bad else "#0e7490"
        o.append(f'<rect x="{px(zx):.1f}" y="{py(zy):.1f}" width="{zw * W:.1f}" height="{zh * H:.1f}" fill="{col}" fill-opacity="0.08" '
                 f'stroke="{col}" stroke-width="2" stroke-dasharray="8 5"/>')
        o.append(f'<text x="{px(zx) + 6:.1f}" y="{py(zy) + 15:.1f}" font-size="11" font-weight="700" fill="{col}">zona livre: {escape(zid)}</text>')

    # entidades, do fundo para a frente
    for plane in V.PLANES:
        for e in [e for e in scene.entities if e.plane == plane]:
            x, y, w, h = e.box
            col = PLANE_COLOR[plane]
            if plan:
                o.append(_floorplan_entity(e, px(x), py(y), w * W, h * H, col))
            else:
                o.append(f'<g><rect x="{px(x):.1f}" y="{py(y):.1f}" width="{w * W:.1f}" height="{h * H:.1f}" rx="6" fill="{col}" fill-opacity="0.22" stroke="{col}" stroke-width="2"/>')
                small = w * W < 120
                ty = py(y) - 5 if small else py(y) + 16
                o.append(f'<text x="{px(x) + (0 if small else 8):.1f}" y="{ty:.1f}" font-size="12" font-weight="600" fill="{INK}">{escape(e.id)}</text></g>')
            raw_pose = next((r.get("pose") for r in scene.data["entities"] if r.get("id") == e.id), None)
            if isinstance(raw_pose, dict):
                o.append(skeleton.mannequin_svg(raw_pose, (px(x), py(y), w * W, h * H)))
            if e.orient and V.DIRECTIONS[e.orient] != (0, 0):
                bx, by = L.anchor_xy(e.box, e.orient, "base")
                tx, ty2 = L.anchor_xy(e.box, e.orient, "tip")
                o.append(f'<line x1="{px(bx):.1f}" y1="{py(by):.1f}" x2="{px(tx):.1f}" y2="{py(ty2):.1f}" stroke="{INK}" stroke-width="2.5" marker-end="url(#arr)"/>')

    # fluxo: rotas, cones de visão e linhas de visão dos asserts
    for i, (name, r) in enumerate(FL.routes(scene.data).items()):
        pts = FL.route_points(scene, r)
        col = FL.ROUTE_COLORS[i % len(FL.ROUTE_COLORS)]
        dash = {"dashed": "10 6", "dotted": "2 6"}.get(r.get("style", "solid"), "")
        path = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in pts)
        o.append(f'<polyline points="{path}" fill="none" stroke="{col}" stroke-width="3" stroke-opacity="0.85"' + (f' stroke-dasharray="{dash}"' if dash else "") + ' stroke-linejoin="round"/>')
        o.append(f'<text x="{px(pts[0][0]) + 6:.1f}" y="{py(pts[0][1]) - 8 - 12 * i:.1f}" font-size="11" font-weight="700" fill="{col}">{escape(str(r.get("label") or name))}</text>')
    for cn in FL.cones(scene.data):
        (cx, cy), ang, spread, rng = FL.cone_geometry(scene, cn)
        pts = [(px(cx), py(cy))] + [(px(cx) + math.cos(ang + spread * (k / 16 - 0.5)) * rng * H, py(cy) + math.sin(ang + spread * (k / 16 - 0.5)) * rng * H) for k in range(17)]
        o.append('<polygon points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '" fill="#dc2626" fill-opacity="0.16" stroke="#dc2626" stroke-width="1.5"/>')
    for r_ in results:
        a_ = parse_assert(r_.raw)
        if a_.name in ("line_of_sight", "occluded"):
            p1, p2 = scene.resolve(a_.args[0]).point, scene.resolve(a_.args[1]).point
            o.append(f'<line x1="{px(p1[0]):.1f}" y1="{py(p1[1]):.1f}" x2="{px(p2[0]):.1f}" y2="{py(p2[1]):.1f}" stroke="{"#15803d" if r_.ok else "#b91c1c"}" stroke-width="2" stroke-dasharray="3 5"/>')

    # âncoras citadas
    for ref in sorted(_referenced_anchors(scene)):
        x, y = scene.resolve(ref).point
        o.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.5" fill="{INK}"/>')
        o.append(f'<text x="{px(x) + 7:.1f}" y="{py(y) - 6:.1f}" font-size="10" fill="{INK}">{escape(ref)}</text>')

    # ordem do olhar
    gaze = scene.data.get("gaze") or []
    if gaze:
        pts = [scene.resolve(g).point for g in gaze]
        path = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in pts)
        o.append(f'<polyline points="{path}" fill="none" stroke="{GAZE}" stroke-width="2" stroke-dasharray="2 6" stroke-linecap="round"/>')
        for i, (x, y) in enumerate(pts, 1):
            o.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="9" fill="{GAZE}"/><text x="{px(x):.1f}" y="{py(y) + 4:.1f}" font-size="11" font-weight="700" fill="#fff" text-anchor="middle">{i}</text>')

    # ponto focal
    fx, fy = scene.focal_target().point
    o.append(f'<circle cx="{px(fx):.1f}" cy="{py(fy):.1f}" r="16" fill="none" stroke="{FOCAL}" stroke-width="3"/>')
    o.append(f'<circle cx="{px(fx):.1f}" cy="{py(fy):.1f}" r="4" fill="{FOCAL}"/>')
    o.append(f'<text x="{px(fx) - 24:.1f}" y="{py(fy) - 22:.1f}" font-size="12" font-weight="700" fill="{FOCAL}" text-anchor="end">foco</text>')

    # contorno do quadro
    o.append(f'{shape} fill="none" stroke="{INK}" stroke-width="2"/>')

    # legenda dos planos
    lx = ox + W - 250
    for i, plane in enumerate(V.PLANES):
        o.append(f'<rect x="{lx:.1f}" y="{oy + H + 10:.1f}" width="12" height="12" fill="{PLANE_COLOR[plane]}" fill-opacity="0.5" stroke="{PLANE_COLOR[plane]}"/>')
        o.append(f'<text x="{lx + 18:.1f}" y="{oy + H + 20:.1f}" font-size="11" fill="{MUTED}">{plane}</text>')
        lx += 90 if i == 0 else 90

    if plan:
        o.extend(_floorplan_panel(scene, ox, oy + H + 40, W))

    # painel de asserts
    y0 = oy + H + 44 + extra_h
    passed = sum(r.ok for r in results)
    o.append(f'<text x="{ox}" y="{y0:.1f}" font-size="14" font-weight="700" fill="{INK}">Asserts: {passed}/{len(results)} cumpridos</text>')
    for i, r in enumerate(results):
        yy = y0 + 22 * (i + 1)
        mark, col = ("✓", "#15803d") if r.ok else ("✗", "#b91c1c")
        o.append(f'<text x="{ox}" y="{yy:.1f}" font-size="13" font-weight="700" fill="{col}">{mark}</text>')
        o.append(f'<text x="{ox + 22}" y="{yy:.1f}" font-size="12" fill="{INK}" font-family="DejaVu Sans Mono, monospace">{escape(r.raw)}</text>')
        o.append(f'<text x="{ox + 22 + 430}" y="{yy:.1f}" font-size="11" fill="{MUTED}">{escape(r.detail)}</text>')
    o.append('</svg>')
    return "\n".join(o)


def svg_to_png(svg_path: str | Path, png_path: str | Path) -> bool:
    """SVG → PNG. Tenta `rsvg-convert`; sem ele, cai para librsvg via `gi` + cairo e, por fim, cairosvg.
    Devolve False (sem erro) se nenhum conversor existir."""
    svg_path, png_path = Path(svg_path), Path(png_path)
    exe = shutil.which("rsvg-convert")
    if exe:
        subprocess.run([exe, "-o", str(png_path), str(svg_path)], check=True)
        return True
    try:
        import cairo  # type: ignore
        import gi  # type: ignore

        gi.require_version("Rsvg", "2.0")
        from gi.repository import Rsvg  # type: ignore

        handle = Rsvg.Handle.new_from_file(str(svg_path))
        dim = handle.get_dimensions()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, int(dim.width)), max(1, int(dim.height)))
        ctx = cairo.Context(surf)
        handle.render_cairo(ctx)
        surf.write_to_png(str(png_path))
        return True
    except Exception:  # noqa: BLE001 - qualquer falha de binding cai para o próximo conversor
        pass
    try:
        import cairosvg  # type: ignore

        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))
        return True
    except Exception:  # noqa: BLE001
        return False


def write_svg_text(svg: str, out: str | Path) -> list[Path]:
    """Grava um SVG já pronto; com .png, converte via rsvg-convert quando existir."""
    out = Path(out)
    if out.suffix.lower() != ".png":
        out.write_text(svg, encoding="utf-8")
        return [out]
    svg_path = out.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    if svg_to_png(svg_path, out):
        return [svg_path, out]
    return [svg_path]


def write_render(scene: Scene, out: str | Path, width: int = 960, style: str = "schematic") -> list[Path]:
    """Grava o SVG e, se `out` termina em .png e há rsvg-convert, o PNG."""
    out = Path(out)
    svg = render_svg(scene, width, style)
    written: list[Path] = []
    if out.suffix.lower() == ".png":
        svg_path = out.with_suffix(".svg")
        svg_path.write_text(svg, encoding="utf-8")
        written.append(svg_path)
        if svg_to_png(svg_path, out):
            written.append(out)
    else:
        out.write_text(svg, encoding="utf-8")
        written.append(out)
    return written
