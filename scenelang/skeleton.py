"""Esqueleto de palitos a partir de `pose`: mostra a pose (ângulos) dentro da caixa da entidade no esquema 2D.

Cinemática direta simples em 3D, projeção ortográfica, giro do corpo por `body_yaw`. É uma conferência visual da
pose declarada, não uma renderização do personagem.
"""
from __future__ import annotations

import math

from .checks import is_num
from .pose import JOINTS, normalize_joint

# comprimentos como fração da altura da figura (cabeça ao pé)
HEAD_R, NECK, TORSO, SHOULDER, HIP = 0.055, 0.05, 0.30, 0.13, 0.07
UPPER_ARM, FOREARM, THIGH, SHIN = 0.17, 0.15, 0.245, 0.235
RIGHT_COL, LEFT_COL, CORE_COL = "#c2410c", "#1d4ed8", "#1f2937"


def _rx(v, a):   # gira em torno de x: um vetor que aponta para cima vai para +z (frente) quando a > 0; um que aponta para baixo vai para -z
    c, s = math.cos(a), math.sin(a)
    return (v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c)


def _rz(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


def _ry(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _g(joints, name, axis):
    v = normalize_joint(joints.get(name), name) if name in joints and name in JOINTS else None
    return math.radians(v.get(axis, 0)) if isinstance(v, dict) and is_num(v.get(axis, 0)) else 0.0


def points(pose: dict) -> dict[str, tuple[float, float, float]]:
    """Posições 3D (x para a direita da imagem, y para cima, z para a câmera) com o quadril na origem."""
    joints = pose.get("joints") or {}
    yaw = math.radians(pose.get("body_yaw", 0) or 0)
    pts: dict[str, tuple] = {"hip": (0.0, 0.0, 0.0)}
    spine_flex, spine_side, spine_twist = _g(joints, "spine", "flex"), _g(joints, "spine", "side"), _g(joints, "spine", "twist")

    def torso(v):   # inclina o tronco; "direita do personagem" é -x na vista de frente
        return _rz(_rx(v, spine_flex), spine_side)

    neck_base = torso((0, TORSO, 0))
    pts["neck"] = neck_base
    head_dir = _rx((0, 1, 0), _g(joints, "neck", "flex"))
    head_dir = _rz(head_dir, _g(joints, "neck", "tilt"))
    pts["head"] = _add(neck_base, head_dir, NECK + HEAD_R)
    face = _ry((0, 0, 1), -_g(joints, "neck", "turn"))   # turn positivo = direita do personagem = -x de frente
    pts["nose"] = _add(pts["head"], face, HEAD_R * 1.3)
    for side, sgn in (("right", -1), ("left", 1)):
        sh = _ry((sgn * SHOULDER, 0, 0), -spine_twist)   # os dois ombros giram o mesmo ângulo: torção p/ a direita leva o esquerdo à frente
        sh = _add(neck_base, sh)
        pts[f"{side}_shoulder"] = sh
        flex, ab, rot = (_g(joints, f"{side}_shoulder", a) for a in ("flex", "abduct", "rotate"))
        up = _rz(_rx((0, -1, 0), -flex), sgn * ab)      # braço pendente: flex + o leva para a frente (+z); abduct + o afasta do corpo
        pts[f"{side}_elbow"] = _add(sh, up, UPPER_ARM)
        e = _g(joints, f"{side}_elbow", "flex")
        fore = _rz(_rx((0, -1, 0), -(flex + e)), sgn * ab)
        pts[f"{side}_wrist"] = _add(pts[f"{side}_elbow"], fore, FOREARM)
        hp = (sgn * HIP, 0.0, 0.0)
        pts[f"{side}_hip"] = hp
        hf, hab = _g(joints, f"{side}_hip", "flex"), _g(joints, f"{side}_hip", "abduct")
        th = _rz(_rx((0, -1, 0), -hf), sgn * hab)
        pts[f"{side}_knee"] = _add(hp, th, THIGH)
        kf = _g(joints, f"{side}_knee", "flex")
        sn = _rz(_rx((0, -1, 0), -(hf - kf)), sgn * hab)
        pts[f"{side}_ankle"] = _add(pts[f"{side}_knee"], sn, SHIN)
    # câmera: quadril na origem; gira o corpo todo em torno de y
    return {k: _ry(v, yaw) for k, v in pts.items()}


def svg(pose: dict, box_px: tuple[float, float, float, float]) -> str:
    """SVG do esqueleto encaixado na caixa (x, y, largura, altura em pixels), pés apoiados na base."""
    x, y, w, h = box_px
    P = points(pose)
    top = max(p[1] for p in P.values()) + HEAD_R
    bot = min(p[1] for p in P.values())
    span = max(top - bot, 1e-6)
    k = h * 0.92 / span
    cx = x + w / 2
    y0 = y + h * 0.04

    def xy(p):
        return cx + p[0] * k, y0 + (top - p[1]) * k

    def seg(a, b, col, wd=3.5):
        (x1, y1), (x2, y2) = xy(P[a]), xy(P[b])
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{wd}" stroke-linecap="round"/>'

    o = ['<g class="pose" opacity="0.9">']
    o.append(seg("hip", "neck", CORE_COL, 4))
    o.append(seg("left_shoulder", "right_shoulder", CORE_COL))
    o.append(seg("left_hip", "right_hip", CORE_COL))
    for side, col in (("right", RIGHT_COL), ("left", LEFT_COL)):
        for a, b in ((f"{side}_shoulder", f"{side}_elbow"), (f"{side}_elbow", f"{side}_wrist"),
                     (f"{side}_hip", f"{side}_knee"), (f"{side}_knee", f"{side}_ankle")):
            o.append(seg(a, b, col))
        wx, wy = xy(P[f"{side}_wrist"])
        o.append(f'<text x="{wx + 5:.1f}" y="{wy + 4:.1f}" font-size="10" font-weight="700" fill="{col}">{"D" if side == "right" else "E"}</text>')
    hx, hy = xy(P["head"])
    nx, ny = xy(P["nose"])
    o.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{HEAD_R * k:.1f}" fill="#fff" fill-opacity="0.6" stroke="{CORE_COL}" stroke-width="2.5"/>')
    o.append(f'<line x1="{hx:.1f}" y1="{hy:.1f}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{CORE_COL}" stroke-width="2" stroke-dasharray="2 2"/>')
    o.append("</g>")
    return "".join(o)


# ---- modo "sólidos": boneco de construção (caixas, cilindros, esferas, cunhas) -----------------------------------
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def solids_svg(pose: dict, box_px: tuple[float, float, float, float]) -> str:
    """Boneco de construção: cabeça = esfera alongada, pescoço/braços/pernas = cilindros afunilados,
    ombros = esferas, tronco e pélvis = caixas, mãos = ovos, pés = cunhas.
    O cilindro mostra a elipse mais ABERTA quando aponta para a câmera (|eixo·z| grande)."""
    x, y, w, h = box_px
    P = points(pose)
    rs, ls, hp, nk = P["right_shoulder"], P["left_shoulder"], P["hip"], P["neck"]
    up = _norm(_sub(nk, hp))
    rt = _norm(_sub(ls, rs))
    fw = _norm(_cross(rt, up))
    # extensões dos sólidos (para caber no quadro)
    ext = [P[k] for k in P] + [P["head"]]
    top = max(p[1] for p in ext) + HEAD_R * 1.2
    bot = min(p[1] for p in ext) - 0.05
    k = h * 0.94 / max(top - bot, 1e-6)
    cx, y0 = x + w / 2, y + h * 0.03

    def xy(p):
        return cx + p[0] * k, y0 + (top - p[1]) * k

    items: list[tuple[float, str]] = []   # (profundidade z, svg) — pintados do mais longe ao mais perto

    def add(z, s):
        items.append((z, s))

    def line(a, b, col, wd=1.8, dash=False):
        (x1, y1), (x2, y2) = xy(a), xy(b)
        d = ' stroke-dasharray="3 3" opacity="0.45"' if dash else ""
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{wd}" stroke-linecap="round"{d}/>'

    def sphere(c, r, col, flat=1.0):
        px_, py_ = xy(c)
        return (f'<ellipse cx="{px_:.1f}" cy="{py_:.1f}" rx="{r * k:.1f}" ry="{r * k * flat:.1f}" fill="#fff" fill-opacity="0.55" '
                f'stroke="{col}" stroke-width="1.8"/>')

    def cylinder(a, b, ra, rb, col):
        """Cilindro afunilado de a (raio ra) a b (raio rb); elipses nas pontas, abertura = |u·z|."""
        u = _norm(_sub(b, a))
        (ax, ay), (bx, by) = xy(a), xy(b)
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        open_ = abs(u[2])
        o = []
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        if L > 1e-6:
            nx, ny = -dy / L, dx / L
            for s in (1, -1):
                o.append(f'<line x1="{ax + nx * ra * k * s:.1f}" y1="{ay + ny * ra * k * s:.1f}" x2="{bx + nx * rb * k * s:.1f}" '
                         f'y2="{by + ny * rb * k * s:.1f}" stroke="{col}" stroke-width="1.8"/>')
        for (px_, py_), r, front in (((ax, ay), ra, u[2] < 0), ((bx, by), rb, u[2] >= 0)):
            ry_ = max(r * k * open_, 0.8)
            dash = "" if front else ' stroke-dasharray="3 3"'
            o.append(f'<ellipse cx="{px_:.1f}" cy="{py_:.1f}" rx="{ry_:.1f}" ry="{r * k:.1f}" '
                     f'transform="rotate({ang:.1f} {px_:.1f} {py_:.1f})" fill="#fff" fill-opacity="0.5" stroke="{col}" stroke-width="1.6"{dash}/>')
        return "".join(o)

    def box(center, axes, dims, col):
        """Caixa com 3 eixos ortonormais (r, u, f) e dimensões (largura, altura, profundidade). Arestas de trás tracejadas."""
        (r_, u_, f_), (dw, dh, dd) = axes, dims
        pts = {}
        for i, sr in enumerate((-1, 1)):
            for j, su in enumerate((-1, 1)):
                for m, sf in enumerate((-1, 1)):
                    pts[(i, j, m)] = tuple(center[t] + r_[t] * sr * dw / 2 + u_[t] * su * dh / 2 + f_[t] * sf * dd / 2 for t in range(3))
        edges = [((i, j, m), (i2, j2, m2)) for (i, j, m) in pts for (i2, j2, m2) in pts
                 if (i, j, m) < (i2, j2, m2) and sum(a != b for a, b in zip((i, j, m), (i2, j2, m2))) == 1]
        o = []
        zc = center[2]
        for a, b in edges:
            back = (pts[a][2] + pts[b][2]) / 2 < zc - 1e-9
            o.append(line(pts[a], pts[b], col, 1.8, dash=back))
        # face de trás/atrás preenchida de leve para dar volume
        poly = [pts[(i, j, m)] for (i, j, m) in ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))]
        pts2 = " ".join(f"{xy(p)[0]:.1f},{xy(p)[1]:.1f}" for p in poly)
        o.insert(0, f'<polygon points="{pts2}" fill="#fff" fill-opacity="0.4" stroke="none"/>')
        return "".join(o)

    def wedge(heel, forward, up_, side, col):
        """Cunha (pé): calcanhar alto, ponta baixa. heel = ponto do tornozelo."""
        hw, tw, ln, hh = 0.04, 0.032, 0.115, 0.05
        v = {}
        for nm, s in (("l", -1), ("r", 1)):
            v["ht" + nm] = tuple(heel[t] + side[t] * s * hw / 2 for t in range(3))
            v["hb" + nm] = tuple(heel[t] + side[t] * s * hw / 2 - up_[t] * hh for t in range(3))
            v["tt" + nm] = tuple(heel[t] + side[t] * s * tw / 2 - up_[t] * hh + forward[t] * ln for t in range(3))
        es = [("htl", "htr"), ("hbl", "hbr"), ("ttl", "ttr"), ("htl", "hbl"), ("htr", "hbr"), ("hbl", "ttl"), ("hbr", "ttr"), ("htl", "ttl"), ("htr", "ttr")]
        return "".join(line(v[a], v[b], col, 1.6, dash=(v[a][2] + v[b][2]) / 2 < heel[2] - 0.04) for a, b in es)

    def egg(a, b, wid, col):
        (ax, ay), (bx, by) = xy(a), xy(b)
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        mx, my = (ax + bx) / 2, (ay + by) / 2
        L = math.hypot(bx - ax, by - ay)
        return (f'<ellipse cx="{mx:.1f}" cy="{my:.1f}" rx="{L / 2:.1f}" ry="{wid * k:.1f}" transform="rotate({ang:.1f} {mx:.1f} {my:.1f})" '
                f'fill="#fff" fill-opacity="0.55" stroke="{col}" stroke-width="1.6"/>')

    # tronco e pélvis: caixas paralelas (mesmos eixos), como no desenho de construção
    tor_c = _mid(hp, nk)
    add(tor_c[2], box(tor_c, (rt, up, fw), (SHOULDER * 2 * 0.95, TORSO * 0.62, 0.085), CORE_COL))
    pel_c = tuple(hp[t] - up[t] * 0.02 for t in range(3))
    add(pel_c[2] - 0.001, box(pel_c, (rt, up, fw), (HIP * 2 * 1.25, 0.075, 0.075), CORE_COL))
    # pescoço e cabeça
    head = P["head"]
    add(nk[2] - 0.001, cylinder(nk, tuple(nk[t] + (head[t] - nk[t]) * 0.8 for t in range(3)), 0.016, 0.016, CORE_COL))
    hx, hy = xy(head)
    hang = math.degrees(math.atan2(-(xy(head)[1] - xy(nk)[1]), xy(head)[0] - xy(nk)[0])) - 90
    nose = P["nose"]
    add(head[2], f'<ellipse cx="{hx:.1f}" cy="{hy:.1f}" rx="{HEAD_R * 0.85 * k:.1f}" ry="{HEAD_R * 1.12 * k:.1f}" '
                 f'transform="rotate({-hang:.1f} {hx:.1f} {hy:.1f})" fill="#fff" fill-opacity="0.6" stroke="{CORE_COL}" stroke-width="2"/>'
                 f'<path d="M {hx:.1f} {hy - HEAD_R * 1.1 * k:.1f} Q {xy(nose)[0] + (xy(nose)[0] - hx) * 0.6:.1f} {hy:.1f} {hx:.1f} {hy + HEAD_R * 1.1 * k:.1f}" '
                 f'fill="none" stroke="{CORE_COL}" stroke-width="1.4"/>'
                 f'<line x1="{hx - HEAD_R * 0.85 * k:.1f}" y1="{hy:.1f}" x2="{hx + HEAD_R * 0.85 * k:.1f}" y2="{hy:.1f}" stroke="{CORE_COL}" stroke-width="1" stroke-dasharray="2 3"/>')
    for side, col, ab in (("right", RIGHT_COL, "D"), ("left", LEFT_COL, "E")):
        sh, el, wr = P[f"{side}_shoulder"], P[f"{side}_elbow"], P[f"{side}_wrist"]
        add(sh[2], sphere(sh, 0.036, col))
        add((sh[2] + el[2]) / 2, cylinder(sh, el, 0.034, 0.028, col))
        add(el[2], sphere(el, 0.026, col))
        add((el[2] + wr[2]) / 2, cylinder(el, wr, 0.028, 0.02, col))
        fd = _norm(_sub(wr, el))
        hand_end = tuple(wr[t] + fd[t] * 0.075 for t in range(3))
        add(wr[2], egg(wr, hand_end, 0.026, col))
        wx, wy = xy(hand_end)
        add(wr[2] + 0.001, f'<text x="{wx + 5:.1f}" y="{wy + 4:.1f}" font-size="10" font-weight="700" fill="{col}">{ab}</text>')
        hi, kn, an = P[f"{side}_hip"], P[f"{side}_knee"], P[f"{side}_ankle"]
        add((hi[2] + kn[2]) / 2, cylinder(hi, kn, 0.05, 0.036, col))
        add(kn[2], sphere(kn, 0.034, col))
        add((kn[2] + an[2]) / 2, cylinder(kn, an, 0.036, 0.024, col))
        add(an[2], wedge(an, fw, up, rt, col))
    items.sort(key=lambda t: t[0])
    return '<g class="pose solids" opacity="0.95">' + "".join(s for _, s in items) + "</g>"


LEGEND = [("Cabeça", "esfera alongada"), ("Pescoço", "cilindro"), ("Ombro", "esfera"), ("Tronco", "caixa alta e fina"),
          ("Pélvis", "caixa larga e fina"), ("Braços e pernas", "cilindros afunilados"), ("Articulações", "esferas/cilindros"),
          ("Mãos", "ovos esmagados"), ("Pés", "cunhas")]


def sheet_svg(pose: dict, title: str = "") -> str:
    """Folha de construção: a pose declarada em 3 vistas (como declarada, de frente e de perfil) + legenda dos sólidos."""
    import copy
    from html import escape

    views = []
    d = pose.get("body_yaw", 0) or 0
    views.append((f"como declarada (giro {d:g}°)", copy.deepcopy(pose)))
    for label, yaw in (("de frente (0°)", 0), ("de perfil (90°)", 90)):
        p = copy.deepcopy(pose)
        p["body_yaw"] = yaw
        views.append((label, p))
    W, H, cw = 1080, 640, 300
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#eef0f3"/>',
         f'<text x="24" y="34" font-size="20" font-weight="700" fill="#1f2937">Formas sólidas — {escape(title)}</text>',
         '<text x="24" y="56" font-size="12" fill="#6b7280">Esquerda/direita do próprio personagem (E azul, D laranja). Tracejado = parte de trás. '
         'A elipse do cilindro fica mais aberta quando o membro aponta para você.</text>']
    for i, (label, p) in enumerate(views):
        x0 = 24 + i * (cw + 12)
        o.append(f'<rect x="{x0}" y="72" width="{cw}" height="420" rx="8" fill="#fff" fill-opacity="0.7" stroke="#cbd5e1"/>')
        o.append(solids_svg(p, (x0, 80, cw, 404)))
        o.append(f'<text x="{x0 + 10}" y="510" font-size="12" font-weight="600" fill="#1f2937">{escape(label)}</text>')
    o.append('<g font-size="12" fill="#1f2937">')
    for i, (a, b) in enumerate(LEGEND):
        o.append(f'<text x="{24 + (i % 3) * 340}" y="{545 + (i // 3) * 22}"><tspan font-weight="700">{a}:</tspan> {b}</text>')
    o.append("</g></svg>")
    return "".join(o)


# ---- modo "manequim": silhueta limpa para referência (sem tracejado, sem rótulos, poucos tons) ------------------------
TONES = {"light": "#d9dde3", "mid": "#aab1bb", "dark": "#7d8591", "deep": "#5b626d"}
SIDE_TONE = {"right": ("#cfd3da", "#a3aab5", "#7a828f"), "left": ("#b7bdc7", "#8e96a3", "#666e7a")}   # (claro, médio, escuro)
LIGHT = _norm((-0.4, 0.8, 0.45))   # luz vinda de cima, da esquerda da imagem e da câmera


def mannequin_svg(pose: dict, box_px: tuple[float, float, float, float], sides: bool = True) -> str:
    """Manequim de blocos preenchidos: só as faces visíveis, 3 tons por forma, sem linhas escondidas nem texto.

    Pensado para ser olhado por um modelo de imagem ou por uma pessoa de relance: silhueta e orientação primeiro."""
    x, y, w, h = box_px
    P = points(pose)
    rs, ls, hp, nk = P["right_shoulder"], P["left_shoulder"], P["hip"], P["neck"]
    up = _norm(_sub(nk, hp))
    rt = _norm(_sub(ls, rs))
    fw = _norm(_cross(rt, up))
    ext = list(P.values())
    top = max(p[1] for p in ext) + HEAD_R * 1.2
    bot = min(p[1] for p in ext) - 0.05
    k = h * 0.94 / max(top - bot, 1e-6)
    cx, y0 = x + w / 2, y + h * 0.03

    def xy(p):
        return cx + p[0] * k, y0 + (top - p[1]) * k

    def pts_str(ps):
        return " ".join(f"{xy(p)[0]:.1f},{xy(p)[1]:.1f}" for p in ps)

    def shade(normal, tones):
        d = sum(a * b for a, b in zip(_norm(normal), LIGHT))
        return tones[0] if d > 0.35 else tones[1] if d > -0.1 else tones[2]

    items: list[tuple[float, str]] = []
    core = ("#cfd3da", "#a3aab5", "#7a828f")

    def poly(ps, fill, z):
        items.append((z, f'<polygon points="{pts_str(ps)}" fill="{fill}" stroke="{fill}" stroke-width="0.8" stroke-linejoin="round"/>'))

    def blob(c, r, fill, z, flat=1.0):
        px_, py_ = xy(c)
        items.append((z, f'<ellipse cx="{px_:.1f}" cy="{py_:.1f}" rx="{r * k:.1f}" ry="{r * k * flat:.1f}" fill="{fill}"/>'))

    def block(center, dims, tones):
        dw, dh, dd = dims
        faces = [((1, 0, 0), rt), ((-1, 0, 0), rt), ((0, 1, 0), up), ((0, -1, 0), up), ((0, 0, 1), fw), ((0, 0, -1), fw)]
        for (a, b, c_), ax in faces:
            n = tuple(ax[t] * (a + b + c_) for t in range(3))
            if n[2] <= 0.02:
                continue
            corners = []
            for u_, v_ in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                vec = [(rt, dw), (up, dh), (fw, dd)]
                fixed = next(i for i, v in enumerate((a, b, c_)) if v)
                free = [i for i in range(3) if i != fixed]
                coef = [0, 0, 0]
                coef[fixed] = (a, b, c_)[fixed]
                coef[free[0]], coef[free[1]] = u_, v_
                corners.append(tuple(center[t] + sum(vec[i][0][t] * coef[i] * vec[i][1] / 2 for i in range(3)) for t in range(3)))
            poly(corners, shade(n, tones), center[2] + n[2] * 0.01)

    def limb(a, b, ra, rb, tones, z):
        """Cápsula afunilada: polígono entre os dois círculos (tangentes) + esferas nas pontas."""
        (ax, ay), (bx, by) = xy(a), xy(b)
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        mid = tones[1]
        if L > 1e-6:
            nx, ny = -dy / L, dx / L
            ps = f"{ax + nx * ra * k:.1f},{ay + ny * ra * k:.1f} {bx + nx * rb * k:.1f},{by + ny * rb * k:.1f} " \
                 f"{bx - nx * rb * k:.1f},{by - ny * rb * k:.1f} {ax - nx * ra * k:.1f},{ay - ny * ra * k:.1f}"
            items.append((z, f'<polygon points="{ps}" fill="{mid}" stroke="{mid}" stroke-width="0.8" stroke-linejoin="round"/>'))
        blob(a, ra, mid, z)
        blob(b, rb, mid, z)

    # tronco e pélvis (blocos paralelos)
    tor_c = _mid(hp, nk)
    block(tor_c, (SHOULDER * 2 * 0.95, TORSO * 0.62, 0.085), core)
    pel_c = tuple(hp[t] - up[t] * 0.02 for t in range(3))
    block(pel_c, (HIP * 2 * 1.25, 0.075, 0.075), core)
    head = P["head"]
    limb(nk, head, 0.02, 0.02, (core[1], core[1], core[2]), min(nk[2], head[2]) - 0.002)
    hx, hy = xy(head)
    hang = math.degrees(math.atan2(-(xy(head)[1] - xy(nk)[1]), xy(head)[0] - xy(nk)[0])) - 90
    nose = P["nose"]
    items.append((head[2] + 0.001, f'<ellipse cx="{hx:.1f}" cy="{hy:.1f}" rx="{HEAD_R * 0.85 * k:.1f}" ry="{HEAD_R * 1.12 * k:.1f}" '
                           f'transform="rotate({-hang:.1f} {hx:.1f} {hy:.1f})" fill="{core[0]}"/>'))
    # marca do rosto: ponto escuro dentro da cabeça, na direção em que o rosto aponta; some quando o rosto está de costas
    face = _norm(_sub(nose, head))
    if face[2] > -0.15:
        fx_, fy_ = xy(tuple(head[t] + face[t] * HEAD_R * 0.6 for t in range(3)))
        items.append((head[2] + 0.002, f'<circle cx="{fx_:.1f}" cy="{fy_:.1f}" r="{HEAD_R * 0.22 * k:.1f}" fill="{core[2]}"/>'))
    for side in ("right", "left"):
        tones = SIDE_TONE[side] if sides else core
        sh, el, wr = P[f"{side}_shoulder"], P[f"{side}_elbow"], P[f"{side}_wrist"]
        limb(sh, el, 0.036, 0.029, tones, (sh[2] + el[2]) / 2)
        limb(el, wr, 0.029, 0.021, tones, (el[2] + wr[2]) / 2)
        fd = _norm(_sub(wr, el))
        hand_end = tuple(wr[t] + fd[t] * 0.075 for t in range(3))
        limb(wr, hand_end, 0.026, 0.02, tones, wr[2] + 0.0003)
        hi, kn, an = P[f"{side}_hip"], P[f"{side}_knee"], P[f"{side}_ankle"]
        limb(hi, kn, 0.05, 0.037, tones, (hi[2] + kn[2]) / 2)
        limb(kn, an, 0.037, 0.025, tones, (kn[2] + an[2]) / 2)
        toe = tuple(an[t] + fw[t] * 0.115 - up[t] * 0.05 for t in range(3))
        heel_b = tuple(an[t] - up[t] * 0.05 for t in range(3))
        poly([an, toe, heel_b], tones[2], an[2])
    items.sort(key=lambda t: t[0])
    return '<g class="pose mannequin">' + "".join(s for _, s in items) + "</g>"


def reference_svg(pose: dict, width: int = 768, height: int = 1024, bg: str = "#f4f5f7") -> str:
    """Imagem de referência limpa: um manequim, fundo liso, sem texto."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
            f'<rect width="{width}" height="{height}" fill="{bg}"/>' + mannequin_svg(pose, (0, 0, width, height)) + "</svg>")
