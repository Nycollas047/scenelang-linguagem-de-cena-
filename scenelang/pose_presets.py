"""Biblioteca de poses-base (`pose.preset`): ângulos em graus, no referencial do próprio personagem (ver `anatomy.FRAME`).

Um preset é só um ponto de partida: `pose.joints` da cena sobrescreve EIXO a EIXO o que o preset define, e `body_yaw`
da cena vence o do preset. Todos os presets cabem nas faixas do perfil `human_adult` (há teste); perfis mais estreitos
ou outras espécies devem sobrescrever o que não couber.

Os valores são convenção de trabalho (poses legíveis e anatomicamente plausíveis), não captura de movimento.
"""
from __future__ import annotations

import copy

PRESETS: dict[str, dict] = {
    "idle": {
        "description": "em pé, relaxado, peso levemente num dos pés",
        "body_yaw": 0,
        "joints": {"left_shoulder": {"flex": 5, "abduct": 8}, "right_shoulder": {"flex": 5, "abduct": 8},
                   "left_elbow": 12, "right_elbow": 12, "left_knee": 4, "right_knee": 8, "neck": {"tilt": 2}},
    },
    "walk": {
        "description": "caminhada em passo médio, braços em contrafase",
        "body_yaw": 0,
        "joints": {"left_hip": {"flex": 25}, "right_hip": {"flex": -15}, "left_knee": 15, "right_knee": 25,
                   "left_ankle": {"flex": -5}, "right_ankle": {"flex": 10},
                   "left_shoulder": {"flex": -20}, "right_shoulder": {"flex": 25}, "left_elbow": 15, "right_elbow": 30,
                   "spine": {"flex": 4, "twist": -6}},
    },
    "run": {
        "description": "corrida, tronco inclinado, braços dobrados em contrafase",
        "body_yaw": 0,
        "joints": {"left_hip": {"flex": 70}, "right_hip": {"flex": -20}, "left_knee": 80, "right_knee": 50,
                   "left_ankle": {"flex": -10}, "right_ankle": {"flex": 15},
                   "left_shoulder": {"flex": -35}, "right_shoulder": {"flex": 45}, "left_elbow": 95, "right_elbow": 90,
                   "spine": {"flex": 15, "twist": -10}, "neck": {"flex": -10}},
    },
    "crouch": {
        "description": "agachado, joelhos e quadris dobrados, tronco para a frente",
        "body_yaw": 0,
        "joints": {"left_hip": {"flex": 100, "abduct": 15}, "right_hip": {"flex": 100, "abduct": 15}, "left_knee": 115, "right_knee": 115,
                   "left_ankle": {"flex": 18}, "right_ankle": {"flex": 18}, "spine": {"flex": 25},
                   "left_shoulder": {"flex": 30}, "right_shoulder": {"flex": 30}, "left_elbow": 30, "right_elbow": 30},
    },
    "sit": {
        "description": "sentado numa cadeira, coxas na horizontal, mãos nas coxas",
        "body_yaw": 0,
        "joints": {"left_hip": {"flex": 90}, "right_hip": {"flex": 90}, "left_knee": 90, "right_knee": 90,
                   "left_ankle": {"flex": 0}, "right_ankle": {"flex": 0},
                   "left_shoulder": {"flex": 25}, "right_shoulder": {"flex": 25}, "left_elbow": 70, "right_elbow": 70},
    },
    "kneel": {
        "description": "ajoelhado num joelho (o direito no chão), olhar à frente",
        "body_yaw": 0,
        "joints": {"left_hip": {"flex": 90}, "left_knee": 90, "right_hip": {"flex": 0}, "right_knee": 100,
                   "left_ankle": {"flex": 0}, "right_ankle": {"flex": -45}, "spine": {"flex": 8},
                   "left_shoulder": {"flex": 20}, "right_shoulder": {"flex": 10}, "left_elbow": 40, "right_elbow": 30},
    },
    "bow": {
        "description": "reverência, tronco dobrado para a frente, braços ao lado",
        "body_yaw": 0,
        "joints": {"spine": {"flex": 45}, "neck": {"flex": 15}, "left_hip": {"flex": 10}, "right_hip": {"flex": 10},
                   "left_shoulder": {"flex": 10}, "right_shoulder": {"flex": 10}, "left_elbow": 10, "right_elbow": 10},
    },
    "strike_overhead": {
        "description": "golpe de cima para baixo com as duas mãos (martelo, machado), ombros elevados",
        "body_yaw": 25,
        "joints": {"left_shoulder": {"flex": 150, "abduct": 15}, "right_shoulder": {"flex": 150, "abduct": 15},
                   "left_elbow": 70, "right_elbow": 70, "spine": {"flex": -10, "twist": 12}, "neck": {"flex": -5},
                   "left_hip": {"flex": 15}, "right_hip": {"flex": -5}, "left_knee": 20, "right_knee": 10},
    },
    "blacksmith_strike": {
        "description": "ferreiro no golpe: martelo erguido na mão direita, mão esquerda estendida à frente segurando a peça",
        "body_yaw": 35,
        "joints": {"right_shoulder": {"flex": 140, "abduct": 20}, "right_elbow": 80,
                   "left_shoulder": {"flex": 60, "abduct": 10}, "left_elbow": 35,
                   "spine": {"flex": 15, "twist": 10}, "neck": {"flex": 15},
                   "left_hip": {"flex": 15}, "right_hip": {"flex": -5}, "left_knee": 20, "right_knee": 10},
    },
    "cast_forward": {
        "description": "conjuração: uma mão projetada à frente, a outra recolhida junto ao peito",
        "body_yaw": 20,
        "joints": {"right_shoulder": {"flex": 80, "abduct": 10}, "right_elbow": 15, "right_wrist": {"flex": 30},
                   "left_shoulder": {"flex": 35, "abduct": 15}, "left_elbow": 100,
                   "spine": {"flex": 5, "twist": 8}, "left_hip": {"flex": 10}, "right_hip": {"flex": -5},
                   "left_knee": 12, "right_knee": 8},
    },
    "guard": {
        "description": "guarda de combate: pés afastados, braços dobrados na frente do peito",
        "body_yaw": 40,
        "joints": {"left_shoulder": {"flex": 60, "abduct": 10}, "right_shoulder": {"flex": 70, "abduct": 15},
                   "left_elbow": 100, "right_elbow": 95, "spine": {"flex": 8}, "neck": {"flex": 5},
                   "left_hip": {"flex": 20, "abduct": 15}, "right_hip": {"flex": -5, "abduct": 20},
                   "left_knee": 30, "right_knee": 15},
    },
    "reach_up": {
        "description": "alcançando algo no alto com a mão direita",
        "body_yaw": 0,
        "joints": {"right_shoulder": {"flex": 165}, "right_elbow": 10, "left_shoulder": {"flex": 5, "abduct": 10},
                   "spine": {"flex": -8, "side": -8}, "neck": {"flex": -20}, "right_ankle": {"flex": -30}},
    },
}


class PresetError(KeyError):
    pass


def names() -> list[str]:
    return sorted(PRESETS)


def _axes(joint: str, v) -> dict:
    """Número → {eixo principal: número}; mapa → cópia do mapa."""
    from . import anatomy as AN

    if isinstance(v, dict):
        return dict(v)
    return {AN.PRIMARY[joint.split("_", 1)[-1] if joint.startswith(("left_", "right_")) else joint]: v}


def resolve(pose: dict) -> dict:
    """Pose com o preset aplicado por baixo de `joints`/`body_yaw` (cópia; a chave `preset` some do resultado)."""
    name = pose.get("preset")
    if name not in PRESETS:
        raise PresetError(name)
    base = copy.deepcopy(PRESETS[name])
    out = {k: v for k, v in pose.items() if k != "preset"}
    joints = {j: _axes(j, v) for j, v in base["joints"].items()}
    for j, v in (pose.get("joints") or {}).items():
        if isinstance(v, dict) or isinstance(v, (int, float)) and not isinstance(v, bool):
            joints.setdefault(j, {}).update(_axes(j, v))      # sobrescreve eixo a eixo
        else:
            joints[j] = v                                       # valor inválido segue adiante para o validador acusar
    out["joints"] = joints
    if "body_yaw" not in out:
        out["body_yaw"] = base["body_yaw"]
    return out
