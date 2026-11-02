"""Protocolo de planejamento: o modelo propõe cores e linhas-guia antes de gerar a imagem.

`plan_request(scene)` devolve o pedido estruturado (o que o modelo deve responder).
`apply_plan(data, proposal)` grava a proposta na cena; a validação confere as regras.
"""
from __future__ import annotations

import copy

from . import guides as G
from . import palette as PAL


def plan_request(scene) -> dict:
    d = scene.data
    out: dict = {"cena": scene.name}
    pal = PAL.plan_request(d)
    if pal:
        out["palette"] = pal
    g = d.get("guides")
    if isinstance(g, dict) and g.get("mode") == "model_proposes":
        heads = G.heads_of(g.get("canon", "stylized"))
        x0, y0, w, h = G.subject_box(scene)
        lines = g.get("lines", G.DEFAULT_LINES)
        names = [n for n in G.LINE_ORDER if n in lines] if lines else []
        out["guides"] = {
            "linhas": names,
            "formato": "y de cada linha como fração da altura do quadro (0 = topo, 1 = base), em ordem crescente",
            "cabecas_de_altura": heads,
            "regra": "(queixo − topo da cabeça) / (pés − topo da cabeça) deve ser 1/cabeças, com tolerância de 4%",
            "area_do_sujeito": {"x": x0, "y": y0, "largura": w, "altura": h},
        }
    if len(out) == 1:
        out["aviso"] = "a cena não pede nada ao modelo (sem palette.mode: model_picks nem guides.mode: model_proposes)"
    out["como_responder"] = "um YAML com as chaves palette (papel: [valores]) e/ou guides (linha: y)"
    return out


def apply_plan(data: dict, proposal: dict) -> dict:
    new = copy.deepcopy(data)
    if not isinstance(proposal, dict):
        raise ValueError("a proposta deve ser um mapa com palette e/ou guides")
    if "palette" in proposal:
        pal = new.setdefault("palette", {})
        space = pal.get("space", "rgb")
        out = {}
        for role, val in proposal["palette"].items():
            out[role] = {space: val} if isinstance(val, list) else val
        pal["proposal"] = out
    if "guides" in proposal:
        new.setdefault("guides", {})["proposal"] = dict(proposal["guides"])
    return new
