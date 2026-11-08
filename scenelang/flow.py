"""Fluxo de jogo (`flow:`): rotas físicas do jogador e cones de visão/tiro, separados do `gaze` (a leitura visual).

flow:
  player_radius: 0.03            # largura do jogador (fração da altura do quadro); `walkable_connected` erode o piso por ela
  routes:
    critical: {label: "Caminho Crítico", style: solid, points: [porta_entrada.center, ponte_central.center, altar]}
    flank:    {label: "Rota de Flanco", style: dashed, points: [...]}
  sight_cones:
    - {source: besta, angle_deg: 45, range: 0.45}      # abre a partir da `orient` da entidade

`points` são referências (entidade, entidade.âncora, região, ponto da grade). Estilos: solid, dashed, dotted, loop (volta ao início).
"""
from __future__ import annotations

import math

from . import phrases as P
from . import vocab as V

KEYS = {"player_radius", "routes", "sight_cones"}
ROUTE_KEYS = {"label", "style", "points"}
CONE_KEYS = {"source", "angle_deg", "range"}
STYLES = ("solid", "dashed", "dotted", "loop")
ROUTE_COLORS = ("#16a34a", "#2563eb", "#ea580c", "#9333ea", "#0891b2", "#be185d")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def routes(data: dict) -> dict[str, dict]:
    f = data.get("flow")
    r = f.get("routes") if isinstance(f, dict) else None
    return {k: v for k, v in r.items() if isinstance(v, dict)} if isinstance(r, dict) else {}


def cones(data: dict) -> list[dict]:
    f = data.get("flow")
    c = f.get("sight_cones") if isinstance(f, dict) else None
    return [x for x in c if isinstance(x, dict)] if isinstance(c, list) else []


def route_points(scene, route: dict) -> list[tuple[float, float]]:
    pts = [scene.resolve(p).point for p in route.get("points", [])]
    if route.get("style") == "loop" and pts:
        pts.append(pts[0])
    return pts


def cone_geometry(scene, cone: dict):
    """(origem, ângulo central em radianos no plano da imagem, abertura em radianos, alcance) — alcance em alturas do quadro."""
    ent = scene.by_id[cone["source"]]
    dx, dy = V.DIRECTIONS[ent.orient]
    return ent.center, math.atan2(dy, dx), math.radians(float(cone["angle_deg"])), float(cone["range"])


def sentences(scene) -> list[str]:
    out = []
    for name, r in routes(scene.data).items():
        try:
            pts = [P.target_phrase(scene, p) for p in r["points"]]
        except Exception:  # noqa: BLE001 - referência quebrada: o validador já acusou
            continue
        label = r.get("label") or name
        loop = " e volta ao início" if r.get("style") == "loop" else ""
        out.append(f"{label}: trilha de passos e desgaste no piso ligando " + ", depois ".join(pts) + loop + ".")
    for cn in cones(scene.data):
        ent = scene.by_id.get(cn.get("source"))
        if ent is None or not ent.orient:
            continue
        out.append(f"{P.cap(ent.label)} cobre um cone de {float(cn['angle_deg']):g}° voltado {V.DIRECTION_PT[ent.orient]} "
                   f"({P.SCREEN_NOTE}), com alcance de {float(cn['range']) * 100:.0f}% da altura do quadro.")
    return out


def check(c, data: dict, scene) -> None:
    f = data.get("flow")
    if f is None:
        return
    if not isinstance(f, dict):
        c.error("$.flow", "deve ser um mapa (player_radius, routes, sight_cones)", got=f)
        return
    for k in f:
        if k not in KEYS:
            c.error(f"$.flow.{k}", "campo desconhecido", got=k, accepted=sorted(KEYS))
    if "player_radius" in f and not (_num(f["player_radius"]) and 0 < f["player_radius"] < 0.5):
        c.error("$.flow.player_radius", "deve ser um número entre 0 e 0,5 (fração da altura do quadro)", got=f["player_radius"])
    rs = f.get("routes")
    if rs is not None:
        if not isinstance(rs, dict) or not rs:
            c.error("$.flow.routes", "deve ser um mapa nome → rota", got=rs)
        else:
            for name, r in rs.items():
                p = f"$.flow.routes.{name}"
                if not isinstance(r, dict):
                    c.error(p, "cada rota deve ser um mapa {label, style, points}", got=r)
                    continue
                for k in r:
                    if k not in ROUTE_KEYS:
                        c.error(f"{p}.{k}", "campo desconhecido", got=k, accepted=sorted(ROUTE_KEYS))
                if r.get("style", "solid") not in STYLES:
                    c.error(f"{p}.style", "estilo de rota desconhecido", got=r.get("style"), accepted=list(STYLES))
                pts = r.get("points")
                if not isinstance(pts, list) or len(pts) < 2:
                    c.error(f"{p}.points", "deve ter ao menos 2 referências", got=pts)
                    continue
                for i, ref in enumerate(pts):
                    if scene is None:
                        continue
                    try:
                        scene.resolve(ref)
                    except Exception as e:  # noqa: BLE001
                        c.error(f"{p}.points[{i}]", str(e), got=ref, accepted=getattr(e, "accepted", None))
    cs = f.get("sight_cones")
    if cs is not None:
        if not isinstance(cs, list) or not cs:
            c.error("$.flow.sight_cones", "deve ser uma lista de {source, angle_deg, range}", got=cs)
            return
        for i, cn in enumerate(cs):
            p = f"$.flow.sight_cones[{i}]"
            if not isinstance(cn, dict):
                c.error(p, "cada cone deve ser um mapa", got=cn)
                continue
            for k in cn:
                if k not in CONE_KEYS:
                    c.error(f"{p}.{k}", "campo desconhecido", got=k, accepted=sorted(CONE_KEYS))
            if not (_num(cn.get("angle_deg")) and 0 < cn["angle_deg"] <= 360):
                c.error(f"{p}.angle_deg", "deve ser um número em (0, 360]", got=cn.get("angle_deg"))
            if not (_num(cn.get("range")) and cn["range"] > 0):
                c.error(f"{p}.range", "deve ser um número positivo (alturas do quadro)", got=cn.get("range"))
            src = cn.get("source")
            if scene is not None and src not in scene.by_id and src not in c.skipped:
                c.error(f"{p}.source", "entidade inexistente", got=src, accepted=sorted(scene.by_id))
            elif scene is not None and src in scene.by_id and not (scene.by_id[src].orient and V.DIRECTIONS[scene.by_id[src].orient] != (0, 0)):
                c.error(f"{p}.source", f"{src} precisa de `orient` (o cone abre a partir dela)", got=src)
