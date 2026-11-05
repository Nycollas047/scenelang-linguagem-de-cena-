"""Pacote único: junta prompt, guia de composição e cena num formato que o modelo de destino aceita.

Nem todo modelo de imagem recebe vários arquivos. Por isso há três formatos, do mais simples ao mais completo:
- texto:  `prompt.txt`, tudo em palavras (qualquer modelo);
- guia:   `guia.png` (uma imagem) + `prompt_com_guia.txt` (modelos que aceitam uma imagem de referência);
- único:  `cena_unica.png`, UM arquivo com o guia no alto e o prompt escrito embaixo, mais prompt e cena nos
          metadados do PNG (para modelos de chat com visão que aceitam uma só imagem; recupere com `scenelang unpack`).
"""
from __future__ import annotations

import shutil
import subprocess
import textwrap
from html import escape
from pathlib import Path

from . import skeleton
from . import vocab as V
from .compile import to_prose

SKIP_KINDS = {"sky", "terrain"}
PLANE_FILL = {"background": ("#c9d1f2", "#8fa0e0"), "midground": ("#bfe3df", "#6cc0b7"), "foreground": ("#f3d9b0", "#e0a24a")}
GUIDE_PREFACE = ("A imagem anexa é só um guia de composição: os retângulos mostram onde cada elemento fica no quadro e o manequim cinza "
                 "mostra a pose. Não copie as cores, as formas cinzas nem os traços do guia; recrie tudo no estilo descrito abaixo.\n\n")


def guide_svg(scene, width: int = 1024, labels: bool = False) -> tuple[str, int, int]:
    ratio = scene.ratio if isinstance(scene.ratio, (int, float)) else scene.ratio[0] / scene.ratio[1]
    W, H = width, round(width / ratio)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#f4f5f7"/>']
    for plane in V.PLANES:
        for e in [e for e in scene.entities if e.plane == plane and e.kind not in SKIP_KINDS]:
            x, y, w, h = e.box
            fill, stroke = PLANE_FILL[plane]
            o.append(f'<rect x="{x * W:.1f}" y="{y * H:.1f}" width="{w * W:.1f}" height="{h * H:.1f}" rx="10" fill="{fill}" '
                     f'fill-opacity="0.55" stroke="{stroke}" stroke-width="2"/>')
            raw = next((r for r in scene.data["entities"] if r.get("id") == e.id), {})
            if isinstance(raw.get("pose"), dict):
                o.append(skeleton.mannequin_svg(raw["pose"], (x * W, y * H, w * W, h * H)))
            if labels:
                o.append(f'<text x="{x * W + 8:.1f}" y="{y * H + 18:.1f}" font-size="14" font-weight="600" fill="#1f2937">{escape(e.label)}</text>')
    o.append("</svg>")
    return "".join(o), W, H


def _png(svg: str, out: Path) -> None:
    exe = shutil.which("rsvg-convert")
    if not exe:
        raise RuntimeError("rsvg-convert não encontrado: instale librsvg para gerar PNG")
    tmp = out.with_suffix(".tmp.svg")
    tmp.write_text(svg, encoding="utf-8")
    try:
        subprocess.run([exe, "-o", str(out), str(tmp)], check=True)
    finally:
        tmp.unlink(missing_ok=True)


def _font(size: int):
    from PIL import ImageFont

    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _metadata(scene, prompt: str, scene_text: str):
    from PIL.PngImagePlugin import PngInfo

    meta = PngInfo()
    meta.add_text("scenelang-cena", scene.name)
    meta.add_text("scenelang-prompt", prompt)
    meta.add_text("scenelang-yaml", scene_text)
    return meta


def pack(scene, scene_text: str, out_dir: str | Path, only: str | None = None, labels: bool | None = None, width: int = 1024) -> list[Path]:
    from PIL import Image, ImageDraw

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prompt = to_prose(scene)
    prompt_guia = GUIDE_PREFACE + prompt
    made: list[Path] = []

    def w(name: str, text: str):
        p = out / name
        p.write_text(text, encoding="utf-8")
        made.append(p)

    if only in (None, "text"):
        w("prompt.txt", prompt)
    if labels is None:   # sem texto no guia quando a imagem vai sozinha ao gerador; com nomes quando o guia e o prompt viajam juntos
        labels = only == "single"
    svg, W, H = guide_svg(scene, width, labels)
    guide_png = out / "guia.png"
    if only in (None, "guide", "single"):
        _png(svg, guide_png)
    if only in (None, "guide"):
        im = Image.open(guide_png)
        im.save(guide_png, pnginfo=_metadata(scene, prompt_guia, scene_text))
        made.append(guide_png)
        w("prompt_com_guia.txt", prompt_guia)
    if only in (None, "single"):
        g = Image.open(guide_png).convert("RGB")
        font, pad, line_h = _font(15), 24, 21
        chars = max(40, int((W - 2 * pad) / 8.2))
        lines: list[str] = []
        for para in prompt_guia.splitlines():
            lines += textwrap.wrap(para, chars) or [""]
        panel_h = pad * 2 + line_h * len(lines)
        canvas = Image.new("RGB", (W, H + panel_h), "#ffffff")
        canvas.paste(g, (0, 0))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, H, W, H + 4], fill="#1f2937")
        for i, ln in enumerate(lines):
            d.text((pad, H + pad + i * line_h), ln, fill="#111827", font=font)
        single = out / "cena_unica.png"
        canvas.save(single, pnginfo=_metadata(scene, prompt_guia, scene_text))
        made.append(single)
        if only == "single" and guide_png.exists():
            guide_png.unlink()
    return made


def unpack(path: str | Path) -> dict[str, str]:
    from PIL import Image

    im = Image.open(path)
    return {k: v for k, v in (im.text or {}).items() if k.startswith("scenelang-")}
