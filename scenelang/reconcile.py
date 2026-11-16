"""Anotação independente da imagem e reconciliação com a cena.

Por que existe: medir com caixas escritas por quem conhece a cena mistura medida e expectativa, e não enxerga o que SOBROU
na imagem (os pilares a mais, a cama que ninguém pediu). Aqui o fluxo tem duas etapas:

1. `annotate-form`: um anotador (pessoa ou outro modelo) descreve TUDO o que vê na imagem, SEM ver a cena: nome livre e caixa.
2. `reconcile`: casa cada objeto anotado com uma entidade da cena (por palavras do nome e pela sobreposição com a caixa
   declarada), deriva as caixas medidas, reavalia os asserts de geometria, confere `count(...)` pela anotação e lista os
   objetos que não casaram (extras) e as entidades que ninguém achou (ausentes).

O casamento é heurístico (palavras e caixa), e a saída mostra cada par com a pontuação para ser auditado. A anotação só é
"independente" se o anotador de fato não viu a cena: o campo `cego` é declarado por ele e não há como a ferramenta verificar.
"""
from __future__ import annotations

import re
import unicodedata

from . import locate as LC
from .assertions import Result, parse_assert, _cmp

FORMAT = "scenelang.anotacao/1"
OUT_FORMAT = "scenelang.reconciliacao/1"
STOP = {"com", "uma", "uns", "umas", "dos", "das", "para", "por", "sobre", "entre", "sem", "que", "seu", "sua", "nos", "nas", "ele", "ela",
        # posição não identifica objeto: "da esquerda" casaria qualquer coisa à esquerda
        "esquerda", "esquerdo", "direita", "direito", "centro", "fundo", "frente", "topo", "lado", "canto", "superior", "inferior"}
MIN_SHARED = 1


class ReconcileError(ValueError):
    pass


def _stems(text: str) -> set[str]:
    t = unicodedata.normalize("NFKD", str(text).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w[:5] for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 3 and w not in STOP}


def _iou(a, b) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


def form_text(image_name: str = "imagem") -> str:
    """Instrução para o anotador. Não menciona a cena de propósito."""
    return f"""# Anotação: {image_name}

Olhe a imagem e liste TODOS os objetos, personagens, estruturas e efeitos distintos que você vê, inclusive os pequenos
e os repetidos. Para cada um dê um nome curto em português e a caixa normalizada de 0 a 1 no formato
[x, y, largura, altura] (x e y no canto superior esquerdo; x cresce para a direita, y para baixo).
Se houver vários iguais, liste cada um separadamente. Não interprete, não explique, não procure nada específico.

Devolva SÓ este JSON (`cego` = true se você NÃO viu a descrição da cena antes de anotar):

{{"formato": "{FORMAT}", "anotador": "seu nome ou modelo", "cego": true,
 "objetos": [{{"nome": "mesa de madeira", "caixa": [0.10, 0.50, 0.30, 0.20]}}]}}
"""


def load(data) -> dict:
    if not isinstance(data, dict) or data.get("formato") != FORMAT:
        raise ReconcileError(f"a anotação deve ser um mapa com formato {FORMAT!r}")
    objs = data.get("objetos")
    if not isinstance(objs, list) or not objs:
        raise ReconcileError("`objetos` deve ser uma lista não vazia")
    for i, o in enumerate(objs):
        if not isinstance(o, dict) or not isinstance(o.get("nome"), str) or not o["nome"].strip():
            raise ReconcileError(f"objetos[{i}]: precisa de `nome` (texto)")
        b = o.get("caixa")
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v for v in b)):
            raise ReconcileError(f"objetos[{i}] ({o['nome']!r}): `caixa` deve ser [x, y, largura, altura] numérico")
        if b[2] <= 0 or b[3] <= 0 or b[0] < -0.01 or b[1] < -0.01 or b[0] + b[2] > 1.01 or b[1] + b[3] > 1.01:
            raise ReconcileError(f"objetos[{i}] ({o['nome']!r}): caixa fora do quadro normalizado (0 a 1)")
        q = o.get("quantidade", 1)
        if not isinstance(q, int) or isinstance(q, bool) or q < 1:
            raise ReconcileError(f"objetos[{i}] ({o['nome']!r}): `quantidade` deve ser um inteiro positivo")
    return data


def _entity_stems(e) -> set[str]:
    return _stems(e.label) | _stems(e.id.replace("_", " ")) | {s for t in e.tags for s in _stems(t)}


def _key_stems(scene, key: str) -> set[str]:
    """Palavras que identificam o grupo de `count(key)`: o glossário, a própria chave e o que todos os rótulos do grupo têm em comum."""
    out = _stems(key) | _stems((scene.data.get("glossary") or {}).get(key, ""))
    group = [e for e in scene.entities if e.kind == key or key in e.tags]
    if group:
        common = set.intersection(*[_stems(e.label) for e in group])
        out |= common
    return out


def reconcile(scene, annotation: dict) -> dict:
    ann = load(annotation)
    objs = [{"nome": o["nome"], "caixa": [float(v) for v in o["caixa"]], "quantidade": o.get("quantidade", 1), "stems": _stems(o["nome"])}
            for o in ann["objetos"]]
    # 1. candidatos: palavras em comum (obrigatório) + sobreposição com a caixa declarada (desempate)
    cands = []
    for e in scene.entities:
        es = _entity_stems(e)
        for j, o in enumerate(objs):
            shared = len(es & o["stems"])
            if shared >= MIN_SHARED:
                cands.append((shared, _iou(e.box, o["caixa"]), e.id, j))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    used_e, used_o, pairs = set(), set(), []
    for shared, iou, eid, j in cands:
        if eid in used_e or j in used_o:
            continue
        used_e.add(eid)
        used_o.add(j)
        pairs.append({"entidade": eid, "objeto": objs[j]["nome"], "palavras_em_comum": shared, "iou_com_a_caixa_declarada": round(iou, 3),
                      "caixa": objs[j]["caixa"]})
    measured = {p["entidade"]: tuple(p["caixa"]) for p in pairs}
    # 2. asserts de geometria sobre as caixas anotadas
    results, skipped = LC.recheck_asserts(scene, measured)
    asserts = [{"raw": r.raw, "ok": r.ok, "detail": r.detail, "fonte": "anotacao"} for r in results]
    # 3. contagens pela anotação (conta objetos anotados, não entidades declaradas)
    for raw in scene.data.get("asserts") or []:
        a = parse_assert(raw)
        if a.name != "count":
            continue
        ks = _key_stems(scene, a.args[0])
        if not ks:
            skipped.append(raw)
            continue
        hit = [o for o in objs if o["stems"] & ks]
        n = sum(o["quantidade"] for o in hit)
        res = Result(raw, _cmp(a.op, n, a.num), f"a anotação tem {n} objeto(s) do grupo: {', '.join(o['nome'] for o in hit) or '-'}")
        asserts.append({"raw": res.raw, "ok": res.ok, "detail": res.detail, "fonte": "anotacao_contagem"})
    extras = [{"nome": o["nome"], "caixa": o["caixa"], "quantidade": o["quantidade"]} for j, o in enumerate(objs) if j not in used_o]
    return {"formato": OUT_FORMAT, "anotador": ann.get("anotador"), "cego": bool(ann.get("cego")), "objetos_anotados": len(objs),
            "casamentos": pairs, "ausentes": [e.id for e in scene.entities if e.id not in used_e],
            "extras": extras, "asserts": asserts, "nao_medidos": list(skipped), "caixas": {k: list(v) for k, v in measured.items()}}


def summary(rec: dict) -> str:
    lines = [f"anotador: {rec['anotador']} ({'cego' if rec['cego'] else 'NÃO cego: viu a cena; a independência não vale'})",
             f"{rec['objetos_anotados']} objeto(s) anotado(s); {len(rec['casamentos'])} casado(s) com a cena"]
    for a in rec["asserts"]:
        lines.append(("✓ " if a["ok"] else "✗ ") + a["raw"] + "  " + a["detail"])
    if rec["extras"]:
        lines.append("na imagem e fora da cena: " + "; ".join(e["nome"] + (f" ×{e['quantidade']}" if e["quantidade"] > 1 else "") for e in rec["extras"]))
    if rec["ausentes"]:
        lines.append("na cena e não achadas na anotação: " + ", ".join(rec["ausentes"]))
    if rec["nao_medidos"]:
        lines.append("sem medir: " + ", ".join(rec["nao_medidos"]))
    return "\n".join(lines)
