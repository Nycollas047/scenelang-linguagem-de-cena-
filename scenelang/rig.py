"""Perfis de rig: nomes dos ossos e calibração dos eixos de um destino 3D/animação.

A pose do scenelang é abstrata (ver anatomy.FRAME). Cada rig tem repouso (T/A-pose), ordem de Euler e sinais de eixo
próprios, e isso só se conhece medindo o modelo. Por isso:
- `to_rig` troca os NOMES das juntas pelos ossos do destino e devolve os ângulos como estão;
- sem `calibration`, o resultado vem marcado `calibrated: false` e com aviso: NÃO aplique no rig como se fosse nativo;
- `calibration` é um mapa osso → eixo → {axis, sign, offset} fornecido por quem conhece o rig; aplicá-lo faz `calibrated: true`.
Os nomes de osso abaixo são os documentados publicamente (Unity HumanBodyBones, Mixamo); confira no seu modelo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import anatomy as AN
from .pose import JOINTS, normalize_joint, split


@dataclass(frozen=True)
class RigProfile:
    name: str
    bones: dict = field(compare=False)       # junta base (shoulder, elbow...) -> nome do osso, com {side}
    notes: str = ""

    def bone(self, joint: str) -> str | None:
        side, base = split(joint)
        tpl = self.bones.get(base)
        if tpl is None:
            return None
        return tpl.format(side=(side or "").capitalize(), side_lower=side or "")


RIGS: dict[str, RigProfile] = {}


def register_rig(r: RigProfile) -> RigProfile:
    RIGS[r.name] = r
    return r


register_rig(RigProfile("scenelang", {k: k for k in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle", "neck", "spine")},
                        "identidade: os próprios nomes de junta"))
register_rig(RigProfile("unity_humanoid", {"shoulder": "{side}UpperArm", "elbow": "{side}LowerArm", "wrist": "{side}Hand", "hip": "{side}UpperLeg",
                                           "knee": "{side}LowerLeg", "ankle": "{side}Foot", "neck": "Neck", "spine": "Spine"},
                        "nomes de UnityEngine.HumanBodyBones"))
register_rig(RigProfile("mixamo", {"shoulder": "mixamorig:{side}Arm", "elbow": "mixamorig:{side}ForeArm", "wrist": "mixamorig:{side}Hand",
                                   "hip": "mixamorig:{side}UpLeg", "knee": "mixamorig:{side}Leg", "ankle": "mixamorig:{side}Foot",
                                   "neck": "mixamorig:Neck", "spine": "mixamorig:Spine"}, "prefixo mixamorig: dos rigs exportados pelo Mixamo"))


def to_rig(pose: dict, rig: str = "scenelang", calibration: dict | None = None) -> dict:
    """{rig, calibrated, frame, root, bones: {osso: {eixo: graus}}, warnings}. Veja o aviso sobre calibração no módulo."""
    if rig not in RIGS:
        raise KeyError(rig)
    prof = RIGS[rig]
    bones: dict[str, dict] = {}
    warnings: list[str] = []
    used_cal = 0
    for joint, raw in (pose.get("joints") or {}).items():
        if joint not in JOINTS:
            warnings.append(f"junta desconhecida ignorada: {joint}")
            continue
        axes = normalize_joint(raw, joint) or {}
        bone = prof.bone(joint)
        if bone is None:
            warnings.append(f"o rig {rig} não tem osso para {joint}")
            continue
        for ax, deg in axes.items():
            rule = ((calibration or {}).get(bone) or {}).get(ax)
            if rule:
                bones.setdefault(bone, {})[rule.get("axis", ax)] = deg * rule.get("sign", 1) + rule.get("offset", 0)
                used_cal += 1
            else:
                bones.setdefault(bone, {})[ax] = deg
    calibrated = bool(calibration) and used_cal > 0 and used_cal == sum(len(normalize_joint(v, j) or {}) for j, v in (pose.get("joints") or {}).items() if j in JOINTS and prof.bone(j))
    if rig != "scenelang" and not calibrated:
        warnings.append("ângulos NÃO calibrados: continuam na convenção do scenelang (neutro = 0° em pé, braços ao lado); o repouso, os eixos e os "
                        "sinais do rig de destino precisam de calibração antes de aplicar")
    return {"rig": rig, "calibrated": calibrated or rig == "scenelang", "frame": AN.FRAME, "profile": pose.get("profile", "human_adult"),
            "root": {"body_yaw": pose.get("body_yaw", 0), "axis": "y"}, "bones": bones, "hold": pose.get("hold") or {}, "warnings": warnings}
