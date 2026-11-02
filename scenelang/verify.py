"""Verificadores de imagem: medem a imagem gerada com código, sem modelo de visão.

verify:
  - max_colors(16)            # no máximo N cores distintas (cores próximas contam como uma)
  - grid_aligned(32)          # a imagem é feita de células N×M nítidas (pixel art de verdade)
  - symmetric(vertical, 0.8)  # simetria do sujeito ≥ 80%
  - fit_guides(0.04)          # topo, pés e eixo do sujeito batem com as linhas-guia (±4% do quadro)
  - palette_match(10)         # ≥ 90% dos pixels do sujeito a ΔE ≤ 10 de uma cor da paleta
  - chroma_clean()            # fundo uniforme na cor da chave
  - no_spill()                # sem cor da chave dentro do sujeito
  - margin(2)                 # células vazias entre o sujeito e a borda

Exige Pillow e numpy (pip install scenelang[image]).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import color as C
from . import fx, guides
from . import palette as PAL
from .checks import is_num, suggest

NAMES = ("max_colors", "grid_aligned", "symmetric", "fit_guides", "palette_match", "chroma_clean", "no_spill", "margin")
ARITY = {"max_colors": (1, 1), "grid_aligned": (0, 2), "symmetric": (1, 2), "fit_guides": (0, 1),
         "palette_match": (1, 2), "chroma_clean": (0, 0), "no_spill": (0, 0), "margin": (1, 1)}
CALL = re.compile(r"^\s*([a-z_]+)\s*\((.*)\)\s*$")


class VerifySyntaxError(ValueError):
    pass


@dataclass
class Check:
    name: str
    args: list
    raw: str


@dataclass
class Result:
    raw: str
    ok: bool
    detail: str
    score: float | None = None


def parse(raw: str) -> Check:
    m = CALL.match(raw)
    if not m:
        raise VerifySyntaxError(f"verificador malformado: {raw!r} (use nome(args), ex.: max_colors(16))")
    name = m.group(1)
    if name not in NAMES:
        raise VerifySyntaxError(f"verificador desconhecido: {name!r}" + (f" — {suggest(name, NAMES)}" if suggest(name, NAMES) else ""))
    args: list = []
    for tok in [t.strip() for t in m.group(2).split(",") if t.strip()]:
        try:
            args.append(float(tok) if "." in tok else int(tok))
        except ValueError:
            args.append(tok)
    lo, hi = ARITY[name]
    if not lo <= len(args) <= hi:
        raise VerifySyntaxError(f"{name} espera {lo if lo == hi else f'{lo} a {hi}'} argumento(s), recebeu {len(args)}: {raw!r}")
    if name == "symmetric" and args[0] != "vertical":
        raise VerifySyntaxError("symmetric só aceita 'vertical' por enquanto")
    nums = args[1:] if name == "symmetric" else args
    if not all(is_num(a) and a > 0 for a in nums):
        raise VerifySyntaxError(f"os argumentos numéricos de {name} devem ser positivos: {raw!r}")
    return Check(name, args, raw)


def check(c, data: dict) -> None:
    v = data.get("verify")
    if v is None:
        return
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        c.error("$.verify", "deve ser uma lista de textos", got=v)
        return
    bg = data.get("background") or {}
    for i, raw in enumerate(v):
        p = f"$.verify[{i}]"
        try:
            ck = parse(raw)
        except VerifySyntaxError as e:
            c.error(p, str(e), got=raw, accepted=list(NAMES))
            continue
        if ck.name == "grid_aligned" and not ck.args and "pixel_grid" not in data.get("canvas", {}):
            c.error(p, "grid_aligned sem argumento exige canvas.pixel_grid", got=raw)
        if ck.name == "margin" and "pixel_grid" not in data.get("canvas", {}):
            c.error(p, "margin exige canvas.pixel_grid", got=raw)
        if ck.name == "fit_guides" and not data.get("guides"):
            c.error(p, "fit_guides exige a camada guides", got=raw)
        if ck.name in ("chroma_clean", "no_spill") and bg.get("mode") != "chromakey":
            c.error(p, f"{ck.name} exige background.mode: chromakey", got=raw)
        if ck.name == "palette_match" and not data.get("palette"):
            c.error(p, "palette_match exige a camada palette", got=raw)


# ---------------------------------------------------------------------------
def _np():
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("os verificadores de imagem exigem Pillow e numpy: pip install pillow numpy") from e
    return np, Image


def _lab(arr):
    np, _ = _np()
    a = arr.astype("float64") / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def _de(lab, ref_rgb):
    np, _ = _np()
    return np.linalg.norm(lab - np.array(C.to_lab(ref_rgb)), axis=-1)


class Frame:
    """Imagem pronta para medir: RGB, laboratório, máscara do fundo e caixa do sujeito."""

    def __init__(self, scene, image):
        np, Image = _np()
        self.scene = scene
        img = image.convert("RGBA")
        self.W, self.H = img.size
        arr = np.asarray(img)
        self.rgb = arr[..., :3]
        self.lab = _lab(self.rgb)
        data = scene.data
        bg = data.get("background") or {}
        self.key = fx.key_color(data)
        self.tol = float(bg.get("tolerance", 12))
        if arr[..., 3].min() < 250:
            self.bg = arr[..., 3] < 128
        elif self.key is not None:
            self.bg = _de(self.lab, self.key) <= self.tol
        else:
            ring = np.concatenate([self.lab[0], self.lab[-1], self.lab[:, 0], self.lab[:, -1]])
            corner = np.median(ring, axis=0)
            self.bg = np.linalg.norm(self.lab - corner, axis=-1) <= 8
        self.fg = ~self.bg
        ys, xs = np.where(self.fg)
        self.bbox = (xs.min() / self.W, ys.min() / self.H, (xs.max() + 1) / self.W, (ys.max() + 1) / self.H) if len(xs) else None
        self.image = img

    def cells(self, n: int):
        """Imagem reduzida à grade de células n × m (amostra no centro de cada célula)."""
        np, Image = _np()
        m = max(1, round(n * self.H / self.W))
        small = self.image.convert("RGB").resize((n, m), Image.NEAREST)
        return np.asarray(small), m


def _cluster_count(rgb_pixels, de: float = 4.0) -> int:
    np, _ = _np()
    uniq = np.unique((rgb_pixels.reshape(-1, 3) // 4) * 4, axis=0)
    reps: list = []
    for u in uniq:
        lab = C.to_lab(tuple(int(x) for x in u))
        if all(((lab[0] - r[0]) ** 2 + (lab[1] - r[1]) ** 2 + (lab[2] - r[2]) ** 2) ** 0.5 > de for r in reps):
            reps.append(lab)
    return len(reps)


# ---- verificadores -----------------------------------------------------------
def v_max_colors(f: Frame, a: list) -> Result:
    n = int(a[0])
    cells = f.scene.data["canvas"].get("pixel_grid")
    src = f.cells(cells)[0] if cells else f.rgb
    k = _cluster_count(src)
    return Result(f"max_colors({n})", k <= n, f"{k} cores distintas (limite {n})", k)


def v_grid_aligned(f: Frame, a: list) -> Result:
    np, Image = _np()
    n = int(a[0]) if a else int(f.scene.data["canvas"]["pixel_grid"])
    need = float(a[1]) if len(a) > 1 else 0.9
    cells, m = f.cells(n)
    up = np.asarray(Image.fromarray(cells).resize((f.W, f.H), Image.NEAREST))
    close = np.linalg.norm(up.astype(int) - f.rgb.astype(int), axis=-1) <= 12
    score = float(close.mean())
    return Result(f"grid_aligned({n})", score >= need, f"{score:.1%} dos pixels batem com uma grade {n}×{m} (mínimo {need:.0%})", score)


def v_symmetric(f: Frame, a: list) -> Result:
    np, _ = _np()
    need = float(a[1]) if len(a) > 1 else 0.8
    if f.bbox is None:
        return Result("symmetric", False, "nenhum sujeito encontrado")
    x0, y0, x1, y1 = (int(round(v)) for v in (f.bbox[0] * f.W, f.bbox[1] * f.H, f.bbox[2] * f.W, f.bbox[3] * f.H))
    sub = f.lab[y0:y1, x0:x1]
    fg = f.fg[y0:y1, x0:x1]
    flip, fgf = sub[:, ::-1], fg[:, ::-1]
    union = fg | fgf
    same = fg & fgf & (np.linalg.norm(sub - flip, axis=-1) <= 8)
    score = float(same.sum() / max(union.sum(), 1))
    return Result(f"symmetric(vertical, {need:g})", score >= need, f"simetria {score:.1%} (mínimo {need:.0%})", score)


def v_fit_guides(f: Frame, a: list) -> Result:
    tol = float(a[0]) if a else 0.04
    lines = guides.guide_lines(f.scene)
    if not lines or f.bbox is None:
        return Result("fit_guides", False, "sem linhas-guia (modo model_proposes sem proposta?) ou sem sujeito")
    ax = guides.axis_x(f.scene)
    top, bottom = f.bbox[1], f.bbox[3]
    errs = []
    if "head_top" in lines:
        errs.append(("topo", top - lines["head_top"]))
    if "baseline" in lines:
        errs.append(("pés", bottom - lines["baseline"]))
    if ax is not None:
        errs.append(("eixo", (f.bbox[0] + f.bbox[2]) / 2 - ax))
    worst = max(abs(e) for _, e in errs)
    txt = ", ".join(f"{n} {e:+.1%}" for n, e in errs)
    return Result(f"fit_guides({tol:g})", worst <= tol, f"desvios: {txt} (tolerância ±{tol:.0%})", worst)


def _palette_for(f: Frame):
    cols = PAL.all_colors(f.scene.data)
    return list(cols.values())


def v_palette_match(f: Frame, a: list) -> Result:
    np, _ = _np()
    de = float(a[0])
    need = float(a[1]) if len(a) > 1 else 0.9
    pal = _palette_for(f)
    if not pal:
        return Result(f"palette_match({de:g})", False, "a paleta não tem cores exatas (rode plan-apply com a proposta do modelo)")
    labs = np.array([C.to_lab(c) for c in pal])
    px = f.lab[f.fg]
    if len(px) == 0:
        return Result(f"palette_match({de:g})", False, "nenhum sujeito encontrado")
    sample = px[:: max(1, len(px) // 20000)]
    dist = np.min(np.linalg.norm(sample[:, None, :] - labs[None], axis=-1), axis=1)
    score = float((dist <= de).mean())
    return Result(f"palette_match({de:g})", score >= need, f"{score:.1%} dos pixels do sujeito a ΔE ≤ {de:g} da paleta (mínimo {need:.0%})", score)


def v_chroma_clean(f: Frame, a: list) -> Result:
    np, _ = _np()
    if f.key is None:
        return Result("chroma_clean", False, "a cena não define chave de chroma")
    b = max(1, int(round(0.02 * min(f.W, f.H))))
    ring = np.zeros((f.H, f.W), bool)
    ring[:b], ring[-b:], ring[:, :b], ring[:, -b:] = True, True, True, True
    inside = _de(f.lab, f.key) <= f.tol
    score = float(inside[ring].mean())
    return Result("chroma_clean()", score >= 0.98, f"{score:.1%} da borda está na cor da chave {C.to_hex(f.key)} (mínimo 98%)", score)


def v_no_spill(f: Frame, a: list) -> Result:
    if f.key is None:
        return Result("no_spill", False, "a cena não define chave de chroma")
    near = (_de(f.lab, f.key) < 45) & f.fg
    score = float(near.sum() / max(f.fg.sum(), 1))
    return Result("no_spill()", score <= 0.005, f"{score:.2%} do sujeito tem cor parecida com a chave (máximo 0,5%)", score)


def v_margin(f: Frame, a: list) -> Result:
    n = int(f.scene.data["canvas"]["pixel_grid"])
    need = int(a[0])
    if f.bbox is None:
        return Result(f"margin({need})", False, "nenhum sujeito encontrado")
    m = max(1, round(n * f.H / f.W))
    left, top = f.bbox[0] * n, f.bbox[1] * m
    right, bottom = n - f.bbox[2] * n, m - f.bbox[3] * m
    least = min(left, top, right, bottom)
    return Result(f"margin({need})", least >= need - 0.25, f"menor margem {least:.1f} célula(s) (mínimo {need})", least)


FUNCS = {"max_colors": v_max_colors, "grid_aligned": v_grid_aligned, "symmetric": v_symmetric, "fit_guides": v_fit_guides,
         "palette_match": v_palette_match, "chroma_clean": v_chroma_clean, "no_spill": v_no_spill, "margin": v_margin}


def run(scene, image) -> list[Result]:
    f = Frame(scene, image)
    out = []
    for raw in scene.data.get("verify", []) or []:
        ck = parse(raw)
        r = FUNCS[ck.name](f, ck.args)
        r.raw = raw
        out.append(r)
    return out


# ---- recorte (alfa) ------------------------------------------------------------
def cutout_chroma(scene, image):
    """RGBA a partir de uma imagem sobre fundo de chroma key (alfa por distância + remoção do vazamento)."""
    np, Image = _np()
    key = fx.key_color(scene.data)
    if key is None:
        raise ValueError("a cena não define background.mode: chromakey")
    tol = float((scene.data.get("background") or {}).get("tolerance", 12))
    rgb = np.asarray(image.convert("RGB")).astype("float64")
    d = _de(_lab(rgb), key)
    alpha = np.clip((d - tol) / (tol * 1.5), 0, 1)
    k = np.array(key, dtype="float64")
    safe = np.maximum(alpha, 1e-3)[..., None]
    fg = np.clip((rgb - (1 - alpha)[..., None] * k) / safe, 0, 255)
    fg = np.where((alpha > 0.02)[..., None], fg, rgb)
    out = np.dstack([fg, alpha * 255]).astype("uint8")
    return Image.fromarray(out, "RGBA")


def cutout_difference(on_black, on_white):
    """RGBA exato pela diferença entre a mesma imagem sobre preto e sobre branco (preserva translucidez)."""
    np, Image = _np()
    b = np.asarray(on_black.convert("RGB")).astype("float64")
    w = np.asarray(on_white.convert("RGB")).astype("float64")
    if b.shape != w.shape:
        raise ValueError("as duas passadas precisam ter o mesmo tamanho")
    alpha = np.clip(1 - (w - b).mean(axis=-1) / 255, 0, 1)
    fg = np.clip(b / np.maximum(alpha, 1e-3)[..., None], 0, 255)
    return Image.fromarray(np.dstack([fg, alpha * 255]).astype("uint8"), "RGBA")
