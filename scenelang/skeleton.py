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


def _rx(v, a):   # gira em torno de x: para baixo → para a frente (+z) quando a > 0
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
        return _rz(_rx(v, spine_flex), -spine_side)

    neck_base = torso((0, TORSO, 0))
    pts["neck"] = neck_base
    head_dir = _rx((0, 1, 0), _g(joints, "neck", "flex"))
    head_dir = _rz(head_dir, -_g(joints, "neck", "tilt"))
    pts["head"] = _add(neck_base, head_dir, NECK + HEAD_R)
    face = _ry((0, 0, 1), -_g(joints, "neck", "turn"))   # turn positivo = direita do personagem = -x de frente
    pts["nose"] = _add(pts["head"], face, HEAD_R * 1.3)
    for side, sgn in (("right", -1), ("left", 1)):
        sh = _ry((sgn * SHOULDER, 0, 0), spine_twist * sgn)
        sh = _add(neck_base, sh)
        pts[f"{side}_shoulder"] = sh
        flex, ab, rot = (_g(joints, f"{side}_shoulder", a) for a in ("flex", "abduct", "rotate"))
        up = _rz(_rx((0, -1, 0), flex), -sgn * ab)
        pts[f"{side}_elbow"] = _add(sh, up, UPPER_ARM)
        e = _g(joints, f"{side}_elbow", "flex")
        fore = _rz(_rx((0, -1, 0), flex + e), -sgn * ab)
        pts[f"{side}_wrist"] = _add(pts[f"{side}_elbow"], fore, FOREARM)
        hp = (sgn * HIP, 0.0, 0.0)
        pts[f"{side}_hip"] = hp
        hf, hab = _g(joints, f"{side}_hip", "flex"), _g(joints, f"{side}_hip", "abduct")
        th = _rz(_rx((0, -1, 0), hf), -sgn * hab)
        pts[f"{side}_knee"] = _add(hp, th, THIGH)
        kf = _g(joints, f"{side}_knee", "flex")
        sn = _rz(_rx((0, -1, 0), hf - kf), -sgn * hab)
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
