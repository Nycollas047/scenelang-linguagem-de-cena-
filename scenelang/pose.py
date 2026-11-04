"""Pose: articulações em graus, com limites anatômicos.

Motivo: modelos de imagem erram a anatomia (cotovelo dobrado para trás, pescoço girado 150°) quando a pose só
existe em prosa. Aqui cada articulação recebe um ângulo e a linguagem rejeita o que o corpo humano não faz.

entities:
  - id: pirata
    kind: character
    pose:
      body_yaw: 135                # giro do corpo na imagem: 0 de frente, 90 perfil olhando p/ direita da imagem,
                                   # -90 perfil p/ esquerda, 180 de costas
      joints:
        right_elbow: 90            # número = eixo principal da junta
        left_shoulder: {flex: 20, abduct: 35}
        neck: {turn: -60}          # cabeça girada em relação ao tronco
        right_knee: 35
      hold: {right_hand: espada}   # opcional: o que cada mão/pé segura ou toca

Convenções (neutro = 0° = anatomia relaxada, em pé, braços ao lado do corpo):
- esquerda/direita são SEMPRE do personagem (não de quem vê a imagem);
- flex: positivo dobra para a frente (cotovelo, joelho, quadril, ombro, tronco); negativo é extensão;
- abduct: positivo afasta do corpo (lateral); turn/twist: positivo gira para o lado direito do personagem;
- tilt/side: positivo inclina para o lado direito do personagem.
"""
from __future__ import annotations

from .checks import closest, is_num, unknown_keys

# junta -> eixo -> (mín, máx, rótulo). Faixas de movimento típicas de adulto (valores ativos, arredondados).
_LIMB = {
    "shoulder": {"flex": (-50, 180), "abduct": (-30, 180), "rotate": (-90, 70)},
    "elbow": {"flex": (0, 150)},
    "wrist": {"flex": (-70, 80), "side": (-20, 30)},
    "hip": {"flex": (-20, 120), "abduct": (-30, 45), "rotate": (-45, 45)},
    "knee": {"flex": (0, 140)},
    "ankle": {"flex": (-50, 20)},
}
_AXIAL = {
    "neck": {"flex": (-50, 60), "turn": (-80, 80), "tilt": (-45, 45)},
    "spine": {"flex": (-30, 80), "twist": (-45, 45), "side": (-35, 35)},
}
JOINTS: dict[str, dict[str, tuple[int, int]]] = dict(_AXIAL)
for _name, _axes in _LIMB.items():
    for _side in ("left", "right"):
        JOINTS[f"{_side}_{_name}"] = _axes

PRIMARY = {"shoulder": "flex", "elbow": "flex", "wrist": "flex", "hip": "flex", "knee": "flex", "ankle": "flex",
           "neck": "turn", "spine": "flex"}

JOINT_PT = {"neck": "o pescoço", "spine": "a coluna", "shoulder": "o ombro", "elbow": "o cotovelo", "wrist": "o punho",
            "hip": "o quadril", "knee": "o joelho", "ankle": "o tornozelo"}
SIDE_PT = {"left": "esquerdo", "right": "direito"}
# (junta, eixo) -> (frase quando positivo, frase quando negativo)
AXIS_PT = {
    "flex": ("dobrado para a frente", "estendido para trás"),
    "abduct": ("afastado do corpo para o lado", "cruzando o corpo"),
    "rotate": ("girado para dentro", "girado para fora"),
    "turn": ("girado para a direita do personagem", "girado para a esquerda do personagem"),
    "twist": ("torcido para a direita do personagem", "torcido para a esquerda do personagem"),
    "tilt": ("inclinado para a direita do personagem", "inclinado para a esquerda do personagem"),
    "side": ("inclinado para a direita do personagem", "inclinado para a esquerda do personagem"),
}
# Dobradiças: só têm um sentido, então a frase muda.
HINGE_PT = {"elbow": "dobrado", "knee": "dobrado"}
HAND_FOOT = {"left_hand": "a mão esquerda", "right_hand": "a mão direita", "left_foot": "o pé esquerdo", "right_foot": "o pé direito"}
POSE_KEYS = {"body_yaw", "joints", "hold"}


def split(joint: str) -> tuple[str | None, str]:
    for s in ("left_", "right_"):
        if joint.startswith(s):
            return s[:-1], joint[len(s):]
    return None, joint


def normalize_joint(v, joint: str) -> dict | None:
    """número → {eixo_principal: número}; mapa → mapa; outro → None."""
    if is_num(v):
        return {PRIMARY[split(joint)[1]]: v}
    return v if isinstance(v, dict) else None


def _band(deg: float, lo: int, hi: int) -> str:
    span = hi if deg >= 0 else -lo
    if span <= 0:
        return ""
    r = abs(deg) / span
    return "leve" if r < 0.25 else "moderado" if r < 0.6 else "acentuado" if r < 0.9 else "no limite"


def check(c, data: dict, scene) -> None:
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict) or "pose" not in e:
            continue
        p = f"$.entities[{i}].pose"
        po = e["pose"]
        if e.get("kind") not in ("character", "creature"):
            c.error(p, "`pose` só vale para kind: character ou creature", got=e.get("kind"))
        if not isinstance(po, dict):
            c.error(p, "deve ser um mapa (body_yaw, joints, hold)", got=po)
            continue
        unknown_keys(c, p, po, POSE_KEYS)
        if "body_yaw" in po:
            v = po["body_yaw"]
            if not is_num(v) or not -180 <= v <= 180:
                c.error(f"{p}.body_yaw", "deve ser um número de -180 a 180 (0 de frente, 90 perfil p/ direita da imagem, 180 de costas)", got=v)
        joints = po.get("joints")
        if joints is not None and not isinstance(joints, dict):
            c.error(f"{p}.joints", "deve ser um mapa junta → ângulo", got=joints)
            joints = None
        for name, raw in (joints or {}).items():
            jp = f"{p}.joints.{name}"
            if name not in JOINTS:
                c.error(jp, "junta desconhecida", got=name, accepted=sorted(JOINTS),
                        hint=f"junta mais parecida: {closest(name, list(JOINTS))}" if closest(name, list(JOINTS)) else None)
                continue
            val = normalize_joint(raw, name)
            if val is None:
                c.error(jp, "deve ser um número (eixo principal) ou um mapa eixo → graus", got=raw)
                continue
            axes = JOINTS[name]
            for ax, deg in val.items():
                ap = f"{jp}.{ax}"
                if ax not in axes:
                    c.error(ap, "eixo inexistente nesta junta", got=ax, accepted=sorted(axes))
                    continue
                if not is_num(deg):
                    c.error(ap, "deve ser um número em graus", got=deg)
                    continue
                lo, hi = axes[ax]
                if not lo <= deg <= hi:
                    clamped = max(lo, min(hi, deg))
                    c.error(ap, f"{deg:g}° é anatomicamente impossível ({name}.{ax}: de {lo}° a {hi}°)", got=deg, accepted=[lo, hi],
                            hint="o modelo tende a quebrar a anatomia fora dessa faixa",
                            fix={"path": jp if is_num(raw) else ap, "value": clamped})
                elif abs(deg) >= 0.9 * (hi if deg >= 0 else -lo) > 0:
                    c.warn(ap, f"{deg:g}° está no limite da junta ({lo}° a {hi}°): pose forçada, o modelo pode errar", hint="alivie alguns graus")
        _coherence(c, p, po, joints or {})
        hold = po.get("hold")
        if hold is not None:
            if not isinstance(hold, dict):
                c.error(f"{p}.hold", "deve ser um mapa mão/pé → texto", got=hold)
            else:
                for k, v in hold.items():
                    if k not in HAND_FOOT:
                        c.error(f"{p}.hold.{k}", "membro desconhecido", got=k, accepted=sorted(HAND_FOOT))
                    elif not isinstance(v, str) or not v.strip():
                        c.error(f"{p}.hold.{k}", "deve ser um texto", got=v)


def _deg(joints: dict, joint: str, axis: str) -> float | None:
    v = normalize_joint(joints.get(joint), joint) if joint in joints else None
    return v.get(axis) if isinstance(v, dict) and is_num(v.get(axis)) else None


def _coherence(c, p: str, po: dict, joints: dict) -> None:
    """Combinações possíveis em cada junta, mas improváveis juntas."""
    neck = _deg(joints, "neck", "turn")
    yaw = po.get("body_yaw")
    # cabeça + corpo viram juntos: soma passa de ~150° de giro de cabeça em relação à câmera é raro mas possível;
    # o erro típico é pedir "rosto visível" com corpo de costas e pescoço quase neutro.
    if is_num(yaw) and neck is not None and abs(yaw) >= 150 and abs(neck) < 50:
        c.warn(f"{p}", "corpo de costas (body_yaw ≥ 150) e pescoço quase neutro: o rosto não aparece", hint="gire o pescoço (turn) 60° ou mais para ver o rosto")
    for side in ("left", "right"):
        hip, knee = _deg(joints, f"{side}_hip", "flex"), _deg(joints, f"{side}_knee", "flex")
        if hip is not None and knee is not None and hip < 0 and knee > 90:
            c.warn(f"{p}.joints.{side}_knee", "perna estendida para trás com joelho muito dobrado: confira se é a pose desejada")
    sh = [_deg(joints, f"{s}_shoulder", "abduct") for s in ("left", "right")]
    sp = _deg(joints, "spine", "flex")
    if sp is not None and sp > 60 and any(x is not None and x > 150 for x in sh):
        c.warn(f"{p}.joints.spine", "tronco muito inclinado com braço quase vertical: pose de equilíbrio difícil, o modelo pode errar")


def _joint_phrase(name: str, axes: dict) -> str:
    side, base = split(name)
    label = JOINT_PT[base] + (f" {SIDE_PT[side]}" if side else "")
    bits = []
    lim = JOINTS[name]
    for ax, deg in axes.items():
        if not deg:
            continue
        pos, neg = AXIS_PT[ax]
        if ax == "flex" and base in HINGE_PT:
            word = HINGE_PT[base]
        else:
            word = pos if deg > 0 else neg
        band = _band(deg, *lim[ax])
        bits.append(f"{word} {abs(deg):g}°" + (f" ({band})" if band else ""))
    return f"{label} " + " e ".join(bits) if bits else ""


def _yaw_phrase(yaw: float) -> str:
    a = abs(yaw)
    side = "para a direita da imagem" if yaw > 0 else "para a esquerda da imagem"
    if a < 15:
        return "corpo de frente para a câmera"
    if a < 60:
        return f"corpo em três quartos de frente, virado {side}"
    if a < 120:
        return f"corpo de perfil, virado {side}"
    if a < 165:
        return f"corpo em três quartos de costas, virado {side}"
    return "corpo de costas para a câmera"


def sentence(scene, entity_id: str) -> str | None:
    raw = next((e for e in scene.data["entities"] if e["id"] == entity_id), {})
    po = raw.get("pose")
    if not isinstance(po, dict):
        return None
    out = []
    if is_num(po.get("body_yaw")):
        out.append(f"{_yaw_phrase(po['body_yaw'])} (giro de {po['body_yaw']:g}°)")
    for name, val in (po.get("joints") or {}).items():
        axes = normalize_joint(val, name) if name in JOINTS else None
        if axes:
            ph = _joint_phrase(name, axes)
            if ph:
                out.append(ph)
    for k, v in (po.get("hold") or {}).items():
        if k in HAND_FOOT:
            out.append(f"{HAND_FOOT[k]} segura/toca {v}")
    if not out:
        return None
    return ("Pose (ângulos em graus a partir da posição neutra, esquerda e direita do próprio personagem; "
            "mantenha a anatomia natural): " + "; ".join(out) + ".")
