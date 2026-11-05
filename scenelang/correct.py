"""Laço de correção automático: imagem gerada → medições → reforço afirmativo → próxima rodada.

Une as medições que já existem (verify, locate, asserts de posição, espelhamento) e transforma cada falha em
uma frase afirmativa (o que deve aparecer, e onde estava errado), que a próxima compilação põe no prompt.
Cada rodada deixa um relatório estruturado: é o dado de avaliação (falha medida por código, sem juiz subjetivo).
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, dataclass

from . import locate as LC
from . import phrases as P
from . import verify as ver
from .assertions import parse_assert

POSITION_PT = {"above": "acima de", "below": "abaixo de", "left_of": "à esquerda de", "right_of": "à direita de",
               "inside": "dentro de", "near": "perto de"}
OPPOSITE_PT = {"above": "abaixo", "below": "acima", "left_of": "à direita", "right_of": "à esquerda"}
MAX_CORRECTIONS = 12


@dataclass
class Finding:
    kind: str          # verify | layout | mirror
    check: str
    ok: bool
    detail: str
    source: str = ""   # assinatura | informada | imagem


def measure(scene, image, boxes: dict | None = None) -> tuple[list[Finding], list[LC.Found]]:
    """Roda todas as medições possíveis. `boxes` são caixas {id: [x,y,w,h]} de quem olhou a imagem."""
    out: list[Finding] = []
    for r in ver.run(scene, image):
        out.append(Finding("verify", r.raw, r.ok, r.detail, "imagem"))
    measured, source = {}, {}
    for k, v in LC.locate_by_signature(scene, image).items():
        measured[k], source[k] = v, "assinatura"
    for k, v in (boxes or {}).items():
        if v is not None and k in scene.by_id:
            measured[k], source[k] = tuple(v), "informada"
    items = LC.compare(scene, measured, source)
    items = [i for i in items if i.source != "assinatura" or LC.reliable(i.declared, i.measured)]
    measured = {i.id: i.measured for i in items}
    if items:
        verdict, detail = LC.mirror_verdict(items)
        if verdict != "incerto":
            out.append(Finding("mirror", "espelhamento", verdict == "ok", f"{verdict} ({detail})",
                               "informada" if all(i.source == "informada" for i in items) else "assinatura"))
        res, _ = LC.recheck_asserts(scene, measured)
        src = "informada" if all(i.source == "informada" for i in items) else "assinatura"
        for r in res:
            out.append(Finding("layout", r.raw, r.ok, r.detail, src))
    return out, items


def _label(scene, ref: str) -> str:
    e = scene.by_id.get(ref.split(".")[0])
    return e.label if e else ref


def _where(scene, ref: str) -> str:
    e = scene.by_id.get(ref)
    return P.entity_position(e, scene.grid_kind) if e else ""


def corrections(scene, findings: list[Finding], items: list[LC.Found]) -> list[str]:
    """Uma frase afirmativa por falha. Fontes por cor (assinatura) viram frases mais cautelosas."""
    out: list[str] = []
    data = scene.data
    for f in findings:
        if f.ok:
            continue
        if f.kind == "mirror":
            ents = sorted((i for i in items), key=lambda i: i.declared[0] + i.declared[2] / 2)
            names = [f"{_label(scene, i.id)} {_where(scene, i.id)}" for i in ents[:3]]
            out.append("A composição saiu espelhada na versão anterior; mantenha " + "; ".join(names)
                       + " (esquerda e direita são as da imagem, de quem a vê).")
        elif f.kind == "layout":
            a = parse_assert(f.check)
            if a.name in POSITION_PT and len(a.args) >= 2:
                A, B = (x.split(".")[0] for x in a.args[:2])
                txt = f"{P.cap(_label(scene, A))} fica {POSITION_PT[a.name]} {_label(scene, B)}"
                if a.name in OPPOSITE_PT:
                    txt += f" (antes ficou {OPPOSITE_PT[a.name]})"
                where = _where(scene, A)
                out.append(txt + (f"; posicione {_label(scene, A)} {where}." if where else "."))
            elif a.name == "visible" and a.args:
                out.append(f"{P.cap(_label(scene, a.args[0]))} aparece inteiro dentro do quadro, sem cortes nas bordas.")
        elif f.kind == "verify":
            name = f.check.split("(")[0]
            if name == "max_colors":
                n = f.check[f.check.index("(") + 1:-1]
                out.append(f"Use no máximo {n} cores na imagem inteira, em áreas chapadas, sem gradiente nem suavização.")
            elif name == "grid_aligned":
                n = f.check[f.check.index("(") + 1:-1].split(",")[0]
                out.append(f"Alinhe cada pixel a uma grade de {n} células de largura; todos os pixels do mesmo tamanho e quadrados, sem meio-pixel.")
            elif name == "palette_match":
                pal = (data.get("palette") or {}).get("colors") or {}
                hexes = ", ".join(str(v) for v in pal.values() if isinstance(v, str))
                out.append("Use somente as cores da paleta" + (f" ({hexes})" if hexes else "")
                           + "; não acrescente tons fora dela.")
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:MAX_CORRECTIONS]


def next_scene(scene, findings: list[Finding], items: list[LC.Found], image_name: str = "") -> tuple[dict, list[str]]:
    """Cena da próxima rodada: correções, reforço de prioridade dos asserts reprovados e histórico."""
    new = copy.deepcopy(scene.data)
    corr = corrections(scene, findings, items)
    asserts = new.get("asserts", [])
    boost = list(new.get("priority_boost", []))
    failed_layout = [f.check for f in findings if f.kind == "layout" and not f.ok and f.check in asserts]
    for raw in failed_layout:
        if raw not in boost:
            boost.append(raw)
    if boost:
        new["priority_boost"] = boost
    new["corrections"] = corr
    hist = list(new.get("history", []))
    hist.append({"rodada": len(hist) + 1, "imagem": image_name, "reprovados": [f.check for f in findings if not f.ok],
                 "tags": []})
    new["history"] = hist
    if not corr:
        new.pop("corrections")
    return new, corr


def report(scene, findings: list[Finding], items: list[LC.Found], image_name: str = "") -> dict:
    """Registro estruturado da rodada (dado de avaliação)."""
    digest = hashlib.sha256(repr(sorted(scene.data.items(), key=lambda kv: kv[0])).encode("utf-8")).hexdigest()[:12]
    return {"cena": scene.name, "hash_cena": digest, "rodada": len(scene.data.get("history", []) or []) + 1, "imagem": image_name,
            "ok": all(f.ok for f in findings), "medicoes": [asdict(f) for f in findings],
            "entidades": [{"id": i.id, "declarada": list(i.declared), "medida": list(i.measured), "fonte": i.source,
                           "iou": round(LC.iou(i.declared, i.measured), 3)} for i in items]}
