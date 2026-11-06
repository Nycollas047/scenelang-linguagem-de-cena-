"""Pacote único: junta prompt, guia de composição e cena num formato que o modelo de destino aceita.

Nem todo modelo de imagem recebe vários arquivos. Por isso há três formatos, do mais simples ao mais completo:
- texto:  `prompt.txt`, tudo em palavras (qualquer modelo);
- guia:   `guia.png` (uma imagem) + `prompt_com_guia.txt` (modelos que aceitam uma imagem de referência);
- único:  `cena_unica.png`, UM arquivo com o guia no alto e o prompt escrito embaixo, mais prompt e cena nos
          metadados do PNG (para modelos de chat com visão que aceitam uma só imagem; recupere com `scenelang unpack`).
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import shutil
import subprocess
from html import escape
from pathlib import Path

from . import canon
from . import color as C
from . import skeleton
from . import vocab as V
from .compile import to_prose

SKIP_KINDS = {"sky", "terrain"}
PLANE_FILL = {"background": ("#c9d1f2", "#8fa0e0"), "midground": ("#bfe3df", "#6cc0b7"), "foreground": ("#f3d9b0", "#e0a24a")}
GUIDE_PREFACE = ("A imagem anexa é só um guia de composição: as áreas coloridas mostram onde cada elemento fica no quadro e o manequim cinza "
                 "mostra a pose. A imagem final é uma ilustração completa, sem molduras, retângulos, áreas coloridas, manequim nem texto "
                 "do guia, e inteiramente no estilo descrito abaixo. O texto abaixo manda: cada elemento é exatamente o descrito, "
                 "sem elementos extras.\n\n")
PACK_VERSION = 1
GUIDE_STYLES = ("blocks", "seg")
# Modalidades de guia previstas (cada uma é um estilo novo em `guide_render`; o manifesto já diz a geometria de cada entidade).
# Ainda NÃO implementadas: pedir uma delas dá erro explícito, nunca um guia aproximado em silêncio.
PLANNED_GUIDE_STYLES = {"mask": "máscaras binárias por entidade", "semantic": "segmentação semântica por classe",
                        "instance": "segmentação por instância (máscara pixel a pixel)", "depth": "mapa de profundidade",
                        "parts": "mapa de partes do corpo (a partir de `pose`)"}
BACKGROUND = "#f4f5f7"
SKIP_REASON = "o tipo {kind} ocupa o quadro todo e não é desenhado no guia (fica só no texto)"
DIM_LIMITS = {"min_side": 256, "max_side": 4096, "max_aspect": 3.0}   # limites conservadores de entrada de geradores
MAX_METADATA_BYTES = 1_000_000
MIN_SEG_DELTA_E = 25.0


class PackError(ValueError):
    pass


def check_dimensions(W: int, H: int) -> list[str]:
    """Avisos sobre o tamanho final: lado mínimo/máximo e proporção que muitos geradores recusam."""
    out = []
    if min(W, H) < DIM_LIMITS["min_side"]:
        out.append(f"lado menor ({min(W, H)} px) abaixo de {DIM_LIMITS['min_side']} px")
    if max(W, H) > DIM_LIMITS["max_side"]:
        out.append(f"lado maior ({max(W, H)} px) acima de {DIM_LIMITS['max_side']} px: o gerador pode reduzir ou recusar a imagem")
    asp = max(W, H) / max(1, min(W, H))
    if asp > DIM_LIMITS["max_aspect"]:
        out.append(f"proporção {asp:.1f}:1 acima de {DIM_LIMITS['max_aspect']:g}:1: o gerador pode cortar a imagem")
    return out


def seg_colors(ids: list[str], min_delta_e: float = MIN_SEG_DELTA_E) -> dict[str, str]:
    """Cor chapada por entidade, determinística e sem colisão.

    O ponto de partida de cada id vem do hash do próprio id (a cor não muda quando outra entidade é acrescentada ou a ordem
    muda); se a cor cai perto demais de uma já usada (ou do fundo), avança em passos de ângulo áureo e, esgotadas as
    tentativas, alterna claridade/saturação. Os ids são processados em ordem alfabética para o resultado não depender da
    ordem de declaração. Devolve {id: '#rrggbb'}.
    """
    if len(set(ids)) != len(ids):
        raise PackError(f"ids duplicados: {sorted({i for i in ids if ids.count(i) > 1})}")
    used: list[tuple[int, int, int]] = [C.parse_color(BACKGROUND)]
    out: dict[str, str] = {}
    thr = min_delta_e
    tiers = [(0.78, 0.92), (0.55, 0.92), (0.80, 0.60), (0.45, 0.78), (0.95, 0.75), (0.65, 0.45)]
    for eid in sorted(ids):
        h0 = int(hashlib.sha256(eid.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        chosen = None
        while chosen is None:
            for step in range(len(tiers) * 24):
                sat, val = tiers[(step // 24) % len(tiers)]
                hue = (h0 + (step % 24) * 0.61803398875) % 1.0
                rgb = tuple(round(v * 255) for v in colorsys.hsv_to_rgb(hue, sat, val))
                if all(C.delta_e(rgb, u) >= thr for u in used):
                    chosen = rgb
                    break
            if chosen is None:
                thr -= 4   # muitas entidades: aceita cores menos distantes, mas nunca iguais
                if thr < 8:
                    raise PackError(f"não há {len(ids)} cores distinguíveis para o guia seg")
        used.append(chosen)
        out[eid] = C.to_hex(chosen)
    return out


def _rect(e):
    return e.box


def _inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def draw_order(scene) -> list:
    """Entidades desenhadas no guia, do fundo para a frente: plano e, dentro do plano, ordem de declaração."""
    return [e for plane in V.PLANES for e in scene.entities if e.plane == plane and e.kind not in SKIP_KINDS]


def guide_info(scene, style: str = "blocks") -> dict:
    """O que o guia contém: entidades (id, cor, caixa, incluída ou não e por quê), sobreposições e entidades ocultas."""
    order = draw_order(scene)
    colors = seg_colors([e.id for e in scene.entities]) if style == "seg" else {}
    ents = []
    for e in scene.entities:
        row = {"id": e.id, "label": e.label, "kind": e.kind, "plane": e.plane, "box": list(e.box), "incluida": e in order,
               "geometria": "caixa"}   # hoje toda entidade é uma caixa; máscaras reais entram aqui como "mascara"
        if not row["incluida"]:
            row["motivo"] = SKIP_REASON.format(kind=e.kind)
        if style == "seg" and row["incluida"]:
            row["cor"] = colors[e.id]
        ents.append(row)
    overlaps = []
    for i, a in enumerate(order):
        for b in order[i + 1:]:          # b é desenhada depois, portanto está na frente de a
            r = _inter(a.box, b.box)
            if r:
                overlaps.append({"atras": a.id, "frente": b.id, "regiao": [round(v, 4) for v in r],
                                 "fracao_de_atras": round(r[2] * r[3] / (a.box[2] * a.box[3]), 3)})
    n = 40
    hidden = []
    for i, a in enumerate(order):
        cells = [(a.box[0] + (x + .5) / n * a.box[2], a.box[1] + (y + .5) / n * a.box[3]) for x in range(n) for y in range(n)]
        front = order[i + 1:]
        vis = sum(not any(f.box[0] <= px < f.box[0] + f.box[2] and f.box[1] <= py < f.box[1] + f.box[3] for f in front) for px, py in cells) / len(cells)
        if vis < 0.5:
            hidden.append({"id": a.id, "visivel": round(vis, 3)})
    return {"entidades": ents, "sobreposicoes": overlaps, "ocultas": hidden, "ordem_de_desenho": [e.id for e in order], "estilo": style}


def _mix(a, b):
    return tuple((x + y) // 2 for x, y in zip(a, b))


def _distinct(rgb, used, thr=18.0):
    """Nudge de claridade até a cor de sobreposição ficar longe de todas as cores de entidade."""
    for k in range(40):
        cand = tuple(max(0, min(255, round(c * (1 + (0.12 if k % 2 else -0.12) * (k // 2 + 1))))) for c in rgb)
        if all(C.delta_e(cand, u) >= thr for u in used):
            return cand
    return rgb


def place_labels(order, W: int, H: int) -> list[tuple[float, float, float, float]]:
    """Posição (x, y, largura, altura) do rótulo de cada entidade; desce o rótulo até não encostar em outro já colocado."""
    placed: list[tuple[float, float, float, float]] = []
    for e in order:
        tw, th = 8.6 * len(e.label) + 8, 20.0
        lx, ly = e.box[0] * W + 8, e.box[1] * H + 6
        for _ in range(len(order) + 6):
            if not any(lx < q[0] + q[2] and q[0] < lx + tw and ly < q[1] + q[3] and q[1] < ly + th for q in placed):
                break
            ly += th + 2
        placed.append((lx, ly, tw, th))
    return placed


def guide_svg(scene, width: int = 1024, labels: bool = False, style: str = "blocks") -> tuple[str, int, int]:
    """style: blocks (retângulos translúcidos com borda) | seg (mapa de segmentação aproximado: áreas chapadas e retangulares,
    sem borda nem texto, uma cor por entidade; a região onde duas entidades se sobrepõem ganha uma terceira cor própria).

    `seg` NÃO é segmentação pixel a pixel: cada entidade ocupa a sua caixa declarada. Máscaras reais são o próximo degrau
    (ver `Mask` em docs/LANGUAGE.md)."""
    svg, W, H, _ = guide_render(scene, width, labels, style)
    return svg, W, H


def guide_render(scene, width: int = 1024, labels: bool = False, style: str = "blocks") -> tuple[str, int, int, dict]:
    if style in PLANNED_GUIDE_STYLES:
        raise PackError(f"estilo de guia {style!r} ({PLANNED_GUIDE_STYLES[style]}) ainda não está implementado; disponíveis: {', '.join(GUIDE_STYLES)}")
    if style not in GUIDE_STYLES:
        raise PackError(f"estilo de guia desconhecido: {style!r} (use {' ou '.join(GUIDE_STYLES)})")
    ratio = scene.ratio if isinstance(scene.ratio, (int, float)) else scene.ratio[0] / scene.ratio[1]
    W, H = width, round(width / ratio)
    info = guide_info(scene, style)
    order = draw_order(scene)
    cols = {r["id"]: r["cor"] for r in info["entidades"] if "cor" in r}
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="{BACKGROUND}"/>']
    for e in order:
        x, y, w, h = e.box
        if style == "seg":
            o.append(f'<rect id="{escape(e.id)}" x="{x * W:.1f}" y="{y * H:.1f}" width="{w * W:.1f}" height="{h * H:.1f}" fill="{cols[e.id]}"/>')
        else:
            fill, stroke = PLANE_FILL[e.plane]
            o.append(f'<rect id="{escape(e.id)}" x="{x * W:.1f}" y="{y * H:.1f}" width="{w * W:.1f}" height="{h * H:.1f}" rx="10" fill="{fill}" '
                     f'fill-opacity="0.55" stroke="{stroke}" stroke-width="2"/>')
        raw = next((r for r in scene.data["entities"] if r.get("id") == e.id), {})
        if isinstance(raw.get("pose"), dict):
            o.append(skeleton.mannequin_svg(raw["pose"], (x * W, y * H, w * W, h * H)))
    if style == "seg":     # sobreposição: região própria, com cor que não é de nenhuma entidade
        used = [C.parse_color(c) for c in cols.values()] + [C.parse_color(BACKGROUND)]
        for ov in info["sobreposicoes"]:
            rgb = _distinct(_mix(C.parse_color(cols[ov["atras"]]), C.parse_color(cols[ov["frente"]])), used)
            used.append(rgb)
            ov["cor"] = C.to_hex(rgb)
            x, y, w, h = ov["regiao"]
            o.append(f'<rect x="{x * W:.1f}" y="{y * H:.1f}" width="{w * W:.1f}" height="{h * H:.1f}" fill="{ov["cor"]}"/>')
    if labels:   # rótulos por último, sem colidir entre si nem ficar atrás de outro elemento
        for e, (lx, ly, _tw, _th) in zip(order, place_labels(order, W, H)):
            o.append(f'<text x="{lx:.1f}" y="{ly + 14:.1f}" font-size="14" font-weight="600" fill="#1f2937" stroke="#ffffff" '
                     f'stroke-width="4" paint-order="stroke">{escape(e.label)}</text>')
    o.append("</svg>")
    return "".join(o), W, H, info


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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta_summary(scene, info: dict, prompt: str, style: str) -> dict:
    """O que viaja dentro do PNG: identifica a cena e as entidades sem depender de outro arquivo."""
    return {"versao_pacote": PACK_VERSION, "hash_cena": canon.scene_hash(scene.data), "hash_algoritmo": canon.ALGORITHM,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "estilo_guia": style, "guia": info}


def _metadata(scene, prompt: str, scene_text: str, info: dict | None = None, style: str = "blocks"):
    from PIL.PngImagePlugin import PngInfo

    summary = _meta_summary(scene, info or guide_info(scene, style), prompt, style)
    meta = PngInfo()
    meta.add_text("scenelang-cena", scene.name)
    meta.add_text("scenelang-prompt", prompt)
    meta.add_text("scenelang-yaml", scene_text)
    meta.add_text("scenelang-hash", summary["hash_cena"])
    meta.add_text("scenelang-manifesto", json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return meta


def _wrap(text: str, font, max_w: float) -> list[str]:
    """Quebra por largura REAL em pixels (não por nº de caracteres); palavra maior que a linha é partida, nunca cortada."""
    lines: list[str] = []
    for para in text.splitlines():
        cur = ""
        for word in para.split(" "):
            cand = (cur + " " + word) if cur else word
            if font.getlength(cand) <= max_w:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            while font.getlength(word) > max_w and len(word) > 1:
                k = len(word)
                while k > 1 and font.getlength(word[:k]) > max_w:
                    k -= 1
                lines.append(word[:k])
                word = word[k:]
            cur = word
        lines.append(cur)
    return lines


def pack(scene, scene_text: str, out_dir: str | Path, only: str | None = None, labels: bool | None = None, width: int = 1024,
         style: str = "blocks", strict: bool = False) -> list[Path]:
    """Grava o pacote e devolve os caminhos. Veja `pack_result` para o manifesto e os avisos."""
    return pack_result(scene, scene_text, out_dir, only, labels, width, style, strict)["files"]


def pack_result(scene, scene_text: str, out_dir: str | Path, only: str | None = None, labels: bool | None = None, width: int = 1024,
                style: str = "blocks", strict: bool = False) -> dict:
    """Como `pack`, mas devolve {files, manifest, warnings}. O que não puder ser preservado vira aviso (ou erro com strict=True)."""
    from PIL import Image, ImageDraw

    if only not in (None, "text", "guide", "single"):
        raise PackError(f"formato desconhecido: {only!r} (use text, guide ou single)")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prompt = to_prose(scene)
    prompt_guia = GUIDE_PREFACE + prompt
    made: list[Path] = []
    warnings: list[str] = []
    dims: dict = {}

    def w(name: str, text: str):
        p = out / name
        p.write_text(text, encoding="utf-8")
        made.append(p)

    if labels is None:   # sem texto no guia quando a imagem vai sozinha ao gerador; com nomes quando o guia e o prompt viajam juntos
        labels = only == "single"
    svg, W, H, info = guide_render(scene, width, labels, style)
    for ent in info["entidades"]:
        if not ent["incluida"]:
            warnings.append(f"{ent['id']}: {ent['motivo']}")
    for hid in info["ocultas"]:
        warnings.append(f"{hid['id']}: só {hid['visivel']:.0%} da caixa fica visível no guia (coberta por entidades à frente)")
    if info["sobreposicoes"] and style == "seg":
        warnings.append(f"{len(info['sobreposicoes'])} sobreposição(ões) marcada(s) com cor própria no guia seg")
    legend = ""
    if style == "seg":
        parts = [f"{r['cor']} = {r['label']}" for r in info["entidades"] if r.get("cor")]
        parts += [f"{ov['cor']} = onde {ov['atras']} e {ov['frente']} se sobrepõem" for ov in info["sobreposicoes"] if ov.get("cor")]
        legend = "Legenda do guia (cor → elemento): " + "; ".join(parts) + ".\n\n"
    prompt_guia = GUIDE_PREFACE + legend + prompt

    if only in (None, "text"):
        w("prompt.txt", prompt)
    guide_png = out / "guia.png"
    if only in (None, "guide", "single"):
        _png(svg, guide_png)
    if only in (None, "guide"):
        im = Image.open(guide_png)
        im.save(guide_png, pnginfo=_metadata(scene, prompt_guia, scene_text, info, style))
        made.append(guide_png)
        w("prompt_com_guia.txt", prompt_guia)
        dims["guia.png"] = [W, H]
    if only in (None, "single"):
        g = Image.open(guide_png).convert("RGB")
        font, pad, line_h = _font(15), 24, 21
        if not hasattr(font, "getlength") or getattr(font, "path", None) is None:
            warnings.append("fonte TrueType não encontrada: o texto do painel usa a fonte padrão e pode perder acentos")
        lines = _wrap(prompt_guia, font, W - 2 * pad)
        panel_h = pad * 2 + line_h * len(lines)
        canvas = Image.new("RGB", (W, H + panel_h), "#ffffff")
        canvas.paste(g, (0, 0))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, H, W, H + 4], fill="#1f2937")
        for i, ln in enumerate(lines):
            d.text((pad, H + pad + i * line_h), ln, fill="#111827", font=font)
        single = out / "cena_unica.png"
        canvas.save(single, pnginfo=_metadata(scene, prompt_guia, scene_text, info, style))
        made.append(single)
        dims["cena_unica.png"] = [W, H + panel_h]
        warnings += [f"cena_unica.png: {m}" for m in check_dimensions(W, H + panel_h)]
        if only == "single" and guide_png.exists():
            guide_png.unlink()
    meta_bytes = len(scene_text.encode("utf-8")) + len(prompt_guia.encode("utf-8"))
    if only in (None, "guide", "single") and meta_bytes > MAX_METADATA_BYTES:
        warnings.append(f"metadados do PNG com {meta_bytes} bytes: alguns serviços removem metadados grandes")
    if strict and warnings:
        for pth in made:
            pth.unlink(missing_ok=True)
        raise PackError("; ".join(warnings))
    manifest = {"versao_pacote": PACK_VERSION, "cena": scene.name, "hash_cena": canon.scene_hash(scene.data), "hash_algoritmo": canon.ALGORITHM,
                "formato": only or "completo", "estilo_guia": style, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "guia": info, "dimensoes": dims, "avisos": warnings}
    if only != "single":     # `single` é, por definição, um arquivo só: tudo viaja nos metadados do PNG
        (out / "cena.yaml").write_text(scene_text, encoding="utf-8")
        made.append(out / "cena.yaml")
        manifest["arquivos"] = {pth.name: {"bytes": pth.stat().st_size, "sha256": _sha(pth)} for pth in made}
        (out / "pacote.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        made.append(out / "pacote.json")
    return {"files": made, "manifest": manifest, "warnings": warnings}


def unpack(path: str | Path) -> dict[str, str]:
    """Metadados `scenelang-*` de um PNG gerado por `pack` (compatibilidade; veja `unpack_checked` para a verificação)."""
    from PIL import Image

    im = Image.open(path)
    return {k: v for k, v in (im.text or {}).items() if k.startswith("scenelang-")}


def unpack_checked(path: str | Path) -> dict:
    """Lê o pacote (um PNG ou a pasta de `pack`) e verifica a integridade: devolve {ok, problems, yaml, prompt, hash_cena, manifest}.
    Nunca devolve 'ok' em silêncio: cada divergência vira um item em `problems`."""
    from .validate import load_text

    path = Path(path)
    problems: list[str] = []
    text = prompt = None
    manifest: dict = {}
    if path.is_dir():
        for name in ("cena.yaml", "pacote.json"):
            if not (path / name).exists():
                problems.append(f"falta {name}")
        if not problems:
            text = (path / "cena.yaml").read_text(encoding="utf-8")
            manifest = json.loads((path / "pacote.json").read_text(encoding="utf-8"))
            for name, meta in (manifest.get("arquivos") or {}).items():
                f = path / name
                if not f.exists():
                    problems.append(f"arquivo do pacote ausente: {name}")
                elif f.name != "pacote.json" and _sha(f) != meta["sha256"]:
                    problems.append(f"{name} mudou desde o pacote (sha256 diferente)")
            if (path / "prompt.txt").exists():
                prompt = (path / "prompt.txt").read_text(encoding="utf-8")
    else:
        meta = unpack(path)
        text, prompt = meta.get("scenelang-yaml"), meta.get("scenelang-prompt")
        if text is None:
            problems.append("o PNG não tem a cena nos metadados (a imagem foi recomprimida ou os metadados foram removidos)")
        try:
            manifest = json.loads(meta["scenelang-manifesto"]) if "scenelang-manifesto" in meta else {}
        except json.JSONDecodeError:
            problems.append("manifesto nos metadados está corrompido")
        if "scenelang-manifesto" not in meta and text is not None:
            problems.append("PNG de versão anterior (sem manifesto): sem como conferir o hash")
    h = None
    if text is not None:
        diags, scene, _ = load_text(text)
        if scene is None:
            problems.append("a cena recuperada não é válida: " + "; ".join(str(d) for d in diags if d.level == "error")[:300])
        else:
            h = canon.scene_hash(scene.data)
            if manifest.get("hash_cena") and manifest["hash_cena"] != h:
                problems.append("o hash da cena recuperada difere do hash registrado no pacote")
            ids = [e.id for e in scene.entities]
            listed = [r["id"] for r in (manifest.get("guia") or {}).get("entidades", [])]
            if listed and listed != ids:
                problems.append(f"entidades do guia {listed} diferem das da cena {ids}")
            if prompt is not None and not prompt.rstrip().endswith(to_prose(scene).rstrip()):
                problems.append("o prompt guardado não corresponde ao que a cena compila hoje")
    return {"ok": not problems, "problems": problems, "yaml": text, "prompt": prompt, "hash_cena": h, "manifest": manifest}
