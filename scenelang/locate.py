"""Localizar: onde cada entidade REALMENTE ficou na imagem, e conferir os asserts de layout contra isso.

Fecha o caso do espelhamento: o `box` declarado diz "pirata à esquerda", a imagem saiu espelhada e nada avisava.

Duas fontes de caixas medidas (use uma ou as duas):
1. `signature` na entidade: 1 a 3 cores que a identificam (ex.: o casaco vermelho). O código acha os pixels dessa cor e
   fica com o maior bloco conexo. Não precisa de modelo de visão; só funciona quando a cor é distintiva.
2. `--boxes achados.json`: caixas informadas por quem olhou a imagem (um detector, um modelo de visão ou uma pessoa).
   `scenelang locate cena.yaml --form` gera o pedido para esse leitor. Formato: {"pirate": [x, y, w, h], ...} normalizado 0..1.

Saída: caixa declarada × medida por entidade, veredito de espelhamento e os asserts de posição reavaliados sobre as caixas medidas.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass

from . import color as C
from . import palette as PAL
from .assertions import evaluate, parse_assert

POSITION_PREDICATES = {"above", "below", "left_of", "right_of", "inside", "near", "visible"}
MIN_AREA = 0.002          # fração do quadro: abaixo disso é ruído, não entidade
SIG_TOL = 14.0            # ΔE (CIE76) aceito em torno da cor-assinatura


@dataclass
class Found:
    id: str
    declared: tuple
    measured: tuple | None
    source: str           # "assinatura" | "informada"

    @property
    def dx(self) -> float | None:
        if not self.measured:
            return None
        return (self.measured[0] + self.measured[2] / 2) - (self.declared[0] + self.declared[2] / 2)


def iou(a, b) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = min(ax2, bx2) - max(a[0], b[0]), min(ay2, by2) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


def _signature_colors(scene, ent_id: str):
    raw = next((e for e in scene.data["entities"] if e["id"] == ent_id), {})
    sig = raw.get("signature")
    if not sig:
        return []
    out = []
    for s in sig if isinstance(sig, list) else [sig]:
        try:
            out.append(PAL.resolve_spec(scene.data, s))
        except C.ColorError:
            try:
                out.append(C.name_to_rgb(str(s)))
            except Exception:
                pass
    return [c for c in out if c is not None]


def locate_by_signature(scene, image) -> dict[str, tuple]:
    from scipy import ndimage

    from .verify import Frame, _de, _np

    np, _ = _np()
    f = Frame(scene, image)
    found = {}
    for e in scene.entities:
        cols = _signature_colors(scene, e.id)
        if not cols:
            continue
        mask = np.zeros(f.rgb.shape[:2], bool)
        for rgb in cols:
            mask |= _de(f.lab, rgb) <= SIG_TOL
        mask = ndimage.binary_opening(mask, iterations=2)
        lab, n = ndimage.label(mask)
        if not n:
            continue
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        # une blocos próximos (casaco + mangas): fica com os que somam ≥ 25% do maior, no entorno do maior
        keep = [i + 1 for i, s in enumerate(sizes) if s >= 0.25 * sizes.max()]
        sel = np.isin(lab, keep)
        if sel.sum() / sel.size < MIN_AREA:
            continue
        ys, xs = np.where(sel)
        x0, x1, y0, y1 = xs.min() / f.W, (xs.max() + 1) / f.W, ys.min() / f.H, (ys.max() + 1) / f.H
        found[e.id] = (round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4))
    return found


def compare(scene, measured: dict[str, tuple], source: dict[str, str] | None = None) -> list[Found]:
    return [Found(e.id, e.box, tuple(measured[e.id]) if e.id in measured else None, (source or {}).get(e.id, "informada"))
            for e in scene.entities if e.id in measured]


def mirror_verdict(items: list[Found]) -> tuple[str, str]:
    """('ok'|'espelhada'|'incerto', detalhe). Compara o erro de x contra o erro com a cena espelhada."""
    pts = [(i.declared[0] + i.declared[2] / 2, i.measured[0] + i.measured[2] / 2) for i in items if i.measured]
    if len(pts) < 2:
        return "incerto", "menos de 2 entidades medidas"
    direct = sum(abs(d - m) for d, m in pts) / len(pts)
    mirrored = sum(abs((1 - d) - m) for d, m in pts) / len(pts)
    spread = max(d for d, _ in pts) - min(d for d, _ in pts)
    if spread < 0.2:
        return "incerto", "entidades quase na mesma coluna: espelhar não muda nada"
    detail = f"erro médio em x: {direct:.2f} como declarada, {mirrored:.2f} se espelhada"
    if mirrored < 0.6 * direct and direct > 0.12:
        return "espelhada", detail
    return "ok", detail


def measured_scene(scene, measured: dict[str, tuple]):
    s2 = copy.copy(scene)
    s2.data = scene.data
    s2.entities = [dataclasses.replace(e, box=tuple(measured[e.id])) if e.id in measured else e for e in scene.entities]
    s2.by_id = {e.id: e for e in s2.entities}
    return s2


def recheck_asserts(scene, measured: dict[str, tuple]):
    """Reavalia os asserts de posição sobre as caixas medidas. Devolve (resultado, ignorado_por_falta_de_medida)."""
    s2 = measured_scene(scene, measured)
    ok, skipped = [], []
    for raw in scene.data.get("asserts") or []:
        a = parse_assert(raw)
        if a.name not in POSITION_PREDICATES:
            continue
        refs = {str(x).split(".")[0] for x in a.args if isinstance(x, str)}
        need = refs & set(scene.by_id)
        if need - set(measured):
            skipped.append(raw)
            continue
        ok.append(evaluate(s2, a))
    return ok, skipped


def form(scene) -> str:
    ents = "\n".join(f'- `{e.id}`: {e.label} ({e.desc[:90]}...)' for e in scene.entities)
    return f"""# Localização na imagem pronta

Olhe a imagem gerada e devolva SÓ um JSON com a caixa de cada item abaixo, normalizada de 0 a 1,
no formato [x, y, largura, altura] com x e y no canto superior esquerdo (x cresce para a direita da imagem, y para baixo).
Se o item não aparece, use null. Não explique.

{ents}

Exemplo: {{"{scene.entities[0].id}": [0.10, 0.20, 0.30, 0.60]}}
"""


def check(c, data: dict) -> None:
    """Valida `signature` nas entidades: 1 a 3 cores."""
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict) or "signature" not in e:
            continue
        p = f"$.entities[{i}].signature"
        sig = e["signature"]
        items = sig if isinstance(sig, list) else [sig]
        if not 1 <= len(items) <= 3:
            c.error(p, "deve ter de 1 a 3 cores", got=sig)
            continue
        for j, s in enumerate(items):
            ok = False
            try:
                ok = PAL.resolve_spec(data, s) is not None
            except C.ColorError:
                ok = isinstance(s, str) and C.name_to_rgb(s.replace("_", "-")) is not None
            if not ok:
                c.error(f"{p}[{j}]", "deve ser uma cor (#rrggbb, rgb, cmyk, hsl, @nome) ou nome de cor em português", got=s)
