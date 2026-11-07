"""Pose em camadas: representação abstrata × perfil anatômico × perfil de rig.

1. Representação abstrata (`pose:` na cena): ângulos em graus, por junta e eixo, no referencial do PRÓPRIO personagem.
2. Perfil anatômico (`pose.profile`): as faixas de movimento permitidas. Trocar o perfil não muda a pose, só o que é aceito.
3. Perfil de rig (`rig.py`): nomes dos ossos e calibração de eixos de um destino (Unity, Mixamo...). Sem calibração a
   conversão devolve os ângulos abstratos, marcados como NÃO calibrados.

Referencial (`FRAME`), usado por pose.py, skeleton.py e pelos exportadores:
- global: x cresce para a direita da IMAGEM, y para cima, z aponta para a câmera; o quadril é a origem;
- `body_yaw` é a única rotação global (em torno de y): 0 = o personagem olha para a câmera (+z), 90 = olha para a direita
  da imagem (+x), -90 = esquerda, 180 = de costas;
- as juntas são LOCAIS (relativas ao segmento pai) e neutro = 0° = em pé, relaxado, braços ao lado do corpo;
- `left`/`right` são sempre do personagem: com body_yaw 0 a direita do personagem fica à esquerda da imagem (-x);
- flex positivo leva o segmento distal para a frente do personagem; abduct positivo o afasta do plano médio; turn/twist/tilt/side
  positivos vão para a direita do personagem.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FRAME = {
    "global": {"x": "direita da imagem", "y": "cima", "z": "para a câmera", "origem": "quadril"},
    "body_yaw": {"eixo": "y", "0": "de frente (olha para +z)", "90": "olha para +x (direita da imagem)", "-90": "olha para -x", "180": "de costas"},
    "juntas": "locais (relativas ao segmento pai); neutro = 0° em pé, relaxado, braços ao lado",
    "lados": "left/right são do personagem (body_yaw 0: a direita do personagem fica em -x)",
    "sinais": {"flex": "+ para a frente do personagem", "abduct": "+ afasta do plano médio", "turn/twist/tilt/side": "+ para a direita do personagem"},
}

# junta -> eixo -> (mín, máx). Faixas de movimento ativo típicas de adulto, arredondadas (uma convenção de trabalho,
# não uma medição clínica: o que importa é que sejam explícitas e substituíveis por outro perfil).
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
PRIMARY = {"shoulder": "flex", "elbow": "flex", "wrist": "flex", "hip": "flex", "knee": "flex", "ankle": "flex", "neck": "turn", "spine": "flex"}


def _expand(limb: dict, axial: dict) -> dict[str, dict[str, tuple[int, int]]]:
    out = dict(axial)
    for name, axes in limb.items():
        for side in ("left", "right"):
            out[f"{side}_{name}"] = axes
    return out


@dataclass(frozen=True)
class AnatomyProfile:
    name: str
    description: str
    limits: dict = field(compare=False)
    note: str = ""

    def range(self, joint: str, axis: str) -> tuple[int, int] | None:
        return (self.limits.get(joint) or {}).get(axis)


def _widen(limits: dict, k: float) -> dict:
    """Amplia cada faixa em k (0 permanece 0 nos lados em que a junta não se move): só para estilização."""
    return {j: {a: (round(lo * k) if lo else lo, round(hi * k) if hi else hi) for a, (lo, hi) in axes.items()} for j, axes in limits.items()}


HUMAN = _expand(_LIMB, _AXIAL)
PROFILES: dict[str, AnatomyProfile] = {}


def register_profile(p: AnatomyProfile) -> AnatomyProfile:
    PROFILES[p.name] = p
    return p


register_profile(AnatomyProfile("human_adult", "humano adulto, faixas ativas típicas", HUMAN,
                                "perfil padrão; as mesmas faixas que o scenelang usa desde a v0.5"))
register_profile(AnatomyProfile("stylized", "personagem estilizado (cartum, jogo): faixas humanas ampliadas em 25%", _widen(HUMAN, 1.25),
                                "convenção de estilo, não dado anatômico; use quando a anatomia humana estrita não se aplica"))


def get_profile(name: str | None) -> AnatomyProfile:
    name = name or "human_adult"
    if name not in PROFILES:
        raise KeyError(name)
    return PROFILES[name]
