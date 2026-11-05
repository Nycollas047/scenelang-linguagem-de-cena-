"""Linha de comando:  python -m scenelang <comando> cena.yaml [opções]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .assertions import evaluate_all
from . import plan as plan_mod
from .compile import BACKENDS, to_prose, to_regions
from .evalform import apply_answers, build_form, dump_scene
from .render import write_render
from .validate import load_file, load_text


def _load(path: str, *, strict: bool = True):
    diags, scene, data = load_file(path)
    for d in diags:
        print(d, file=sys.stderr)
    if scene is None:
        print(f"\n{sum(d.level == 'error' for d in diags)} erro(s): a cena não é válida.", file=sys.stderr)
        sys.exit(1)
    return scene, diags


def cmd_validate(a) -> int:
    if a.fix:
        from . import api

        text = Path(a.scene).read_text(encoding="utf-8")
        res = api.fix(text)
        for line in res["applied"]:
            print(f"corrigido: {line}", file=sys.stderr)
        if not res["applied"]:
            print("nada a corrigir automaticamente.", file=sys.stderr)
        elif a.out:
            Path(a.out).write_text(res["text"], encoding="utf-8")
            print(f"gravado: {a.out}", file=sys.stderr)
            a.scene = a.out
        else:
            bak = Path(a.scene).with_suffix(Path(a.scene).suffix + ".bak")   # a regravação perde comentários: guarda o original
            bak.write_text(text, encoding="utf-8")
            print(f"cópia do original: {bak}", file=sys.stderr)
            Path(a.scene).write_text(res["text"], encoding="utf-8")
            print(f"gravado: {a.scene}", file=sys.stderr)
    diags, scene, _ = load_file(a.scene)
    if a.json:
        print(json.dumps([d.to_dict() for d in diags], ensure_ascii=False, indent=2))
    else:
        for d in diags:
            print(d)
    errors = sum(d.level == "error" for d in diags)
    warns = sum(d.level == "warning" for d in diags)
    if not a.json:
        print(f"\n{'OK' if scene else 'INVÁLIDA'}: {errors} erro(s), {warns} aviso(s).")
    return 0 if scene else 1


def cmd_primer(a) -> int:
    from . import primer

    sys.stdout.write(primer.primer())
    return 0


def cmd_vocab(a) -> int:
    from . import primer

    v = primer.vocab()
    if a.json:
        print(json.dumps(v, ensure_ascii=False, indent=2))
    else:
        for k, vals in v.items():
            print(f"{k}: {', '.join(vals)}")
    return 0


def cmd_new(a) -> int:
    from . import templates

    if a.template is None:
        print("modelos: " + ", ".join(templates.names()))
        return 0
    try:
        text = templates.get(a.template)
    except KeyError:
        print(f"modelo desconhecido: {a.template!r} (disponíveis: {', '.join(templates.names())})", file=sys.stderr)
        return 1
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"gravado: {a.out}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_compile(a) -> int:
    scene, _ = _load(a.scene)
    if a.loss or a.strict:
        from . import loss as LS

        items = LS.report(scene, a.target)
        for it in items:
            print(it, file=sys.stderr)
        if a.strict and LS.blocking(items):
            print("modo estrito: há perdas ou falta de asserts; nada foi compilado", file=sys.stderr)
            return 3
    if a.target == "regions":
        out = to_regions(scene, a.size, a.passname)
    else:
        out = BACKENDS[a.target](scene, a.passname)
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"gravado: {a.out}")
    else:
        sys.stdout.write(out)
    return 0


def cmd_check(a) -> int:
    scene, _ = _load(a.scene)
    results = evaluate_all(scene)
    for r in results:
        print(f"{'✓' if r.ok else '✗'} {r.raw:<52} {r.detail}")
    passed = sum(r.ok for r in results)
    print(f"\n{passed}/{len(results)} asserts cumpridos no layout.")
    return 0 if passed == len(results) else 1


def cmd_render(a) -> int:
    scene, _ = _load(a.scene)
    for p in write_render(scene, a.out, a.width):
        print(f"gravado: {p}")
    return 0


def cmd_eval_form(a) -> int:
    scene, _ = _load(a.scene)
    text = build_form(scene, a.round)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"gravado: {a.out}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_eval_apply(a) -> int:
    scene, _ = _load(a.scene)
    new, failed = apply_answers(scene, Path(a.answers).read_text(encoding="utf-8"), a.lock_passed)
    text = dump_scene(new)
    # a cena atualizada precisa continuar válida
    diags, ok_scene, _ = load_text(text)
    if ok_scene is None:
        for d in diags:
            print(d, file=sys.stderr)
        return 1
    out = a.out or str(Path(a.scene).with_suffix(".next.yaml"))
    Path(out).write_text(text, encoding="utf-8")
    print(f"{len(failed)} item(ns) reprovado(s); cena atualizada em {out}")
    for f in failed:
        print(f"  ✗ {f['assert']}" + (f"  [{f['tag']}]" if f["tag"] else ""))
        print(f"      dica: {f['dica']}")
    return 0


def cmd_plan(a) -> int:
    scene, _ = _load(a.scene)
    sys.stdout.write(json.dumps(plan_mod.plan_request(scene), ensure_ascii=False, indent=2) + "\n")
    return 0


def cmd_plan_apply(a) -> int:
    import yaml

    scene, _ = _load(a.scene)
    proposal = yaml.safe_load(Path(a.proposal).read_text(encoding="utf-8"))
    new = plan_mod.apply_plan(scene.data, proposal)
    text = dump_scene(new)
    diags, ok_scene, _ = load_text(text)
    for d in diags:
        print(d, file=sys.stderr)
    if ok_scene is None:
        print("\nproposta recusada: a cena com a proposta não é válida.", file=sys.stderr)
        return 1
    out = a.out or str(Path(a.scene).with_suffix(".planned.yaml"))
    Path(out).write_text(text, encoding="utf-8")
    print(f"proposta aceita; cena gravada em {out}")
    return 0


def cmd_verify(a) -> int:
    from PIL import Image

    from . import verify as ver

    scene, _ = _load(a.scene)
    results = ver.run(scene, Image.open(a.image))
    if a.json:
        print(json.dumps([{"verify": r.raw, "ok": r.ok, "detail": r.detail, "score": r.score} for r in results], ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"{'✓' if r.ok else '✗'} {r.raw:<28} {r.detail}")
        print(f"\n{sum(r.ok for r in results)}/{len(results)} verificações cumpridas.")
    return 0 if all(r.ok for r in results) else 1


def cmd_locate(a) -> int:
    from . import locate as LC

    scene, _ = _load(a.scene)
    if a.form:
        sys.stdout.write(LC.form(scene))
        return 0
    if not a.image:
        print("informe a imagem (ou use --form para gerar o pedido de localização)", file=sys.stderr)
        return 2
    from PIL import Image

    measured, source = {}, {}
    img = Image.open(a.image)
    for k, v in LC.locate_by_signature(scene, img).items():
        measured[k], source[k] = v, "assinatura"
    if a.boxes:
        for k, v in json.loads(Path(a.boxes).read_text(encoding="utf-8")).items():
            if v is not None and k in scene.by_id:
                measured[k], source[k] = tuple(v), "informada"
    items = LC.compare(scene, measured, source)
    weak = {i.id for i in items if i.source == "assinatura" and not LC.reliable(i.declared, i.measured)}
    for i in items:
        if i.id in weak:
            print(f"· {i.id}: medida por cor pouco confiável (caixa {i.measured[2] * i.measured[3] / (i.declared[2] * i.declared[3]):.1f}× a declarada); ignorada",
                  file=sys.stderr)
    items = [i for i in items if i.id not in weak]
    measured = {i.id: i.measured for i in items}
    if not items:
        print("nenhuma entidade localizada: declare `signature` nas entidades ou passe --boxes", file=sys.stderr)
        return 2
    for it in items:
        d, m = it.declared, it.measured
        print(f"{it.id:<12} declarada x={d[0]:.2f} y={d[1]:.2f} w={d[2]:.2f} h={d[3]:.2f} | medida x={m[0]:.2f} y={m[1]:.2f} w={m[2]:.2f} h={m[3]:.2f} "
              f"| IoU {LC.iou(d, m):.2f} ({it.source})")
    verdict, detail = LC.mirror_verdict(items)
    print(f"\nespelhamento: {verdict} ({detail})")
    res, skipped = LC.recheck_asserts(scene, measured)
    for r in res:
        print(f"{'✓' if r.ok else '✗'} {r.raw:<40} {r.detail}")
    for raw in skipped:
        print(f"· {raw:<40} sem medida de todas as entidades")
    bad = verdict == "espelhada" or any(not r.ok for r in res)
    return 1 if bad else 0


def cmd_pose(a) -> int:
    from . import skeleton

    scene, _ = _load(a.scene)
    raw = next((e for e in scene.data["entities"] if e.get("id") == a.entity), None)
    if raw is None or not isinstance(raw.get("pose"), dict):
        print(f"a entidade {a.entity!r} não existe ou não tem `pose`", file=sys.stderr)
        return 2
    from . import render as R

    if a.style == "construction":
        svg = skeleton.sheet_svg(raw["pose"], a.entity)
    else:   # manequim: uma figura limpa, própria para servir de referência
        svg = skeleton.reference_svg(raw["pose"])
    for path in R.write_svg_text(svg, a.out):
        print(f"gravado: {path}")
    return 0


def cmd_correct(a) -> int:
    from PIL import Image

    from . import correct as CR

    scene, _ = _load(a.scene)
    boxes = json.loads(Path(a.boxes).read_text(encoding="utf-8")) if a.boxes else None
    img = Image.open(a.image)
    findings, items = CR.measure(scene, img, boxes)
    if not findings:
        print("nada a medir: declare `verify`, `signature` nas entidades ou passe --boxes", file=sys.stderr)
        return 2
    for f in findings:
        print(f"{'✓' if f.ok else '✗'} [{f.kind}] {f.check:<34} {f.detail}" + (f"  ({f.source})" if f.source and f.kind != "verify" else ""))
    new, corr = CR.next_scene(scene, findings, items, Path(a.image).name)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "relatorio.json").write_text(json.dumps(CR.report(scene, findings, items, Path(a.image).name), ensure_ascii=False, indent=2), encoding="utf-8")
    from .evalform import dump_scene

    new_text = dump_scene(new)
    diags, ok_scene, _ = load_text(new_text)
    if ok_scene is None:
        for d in diags:
            print(d, file=sys.stderr)
        return 1
    (out / "cena.next.yaml").write_text(new_text, encoding="utf-8")
    (out / "prompt_next.txt").write_text(to_prose(ok_scene), encoding="utf-8")
    ok = all(f.ok for f in findings)
    print(f"\n{sum(f.ok for f in findings)}/{len(findings)} medições cumpridas; {len(corr)} correção(ões) para a próxima rodada.")
    print(f"gravado em {out}: relatorio.json, cena.next.yaml, prompt_next.txt")
    return 0 if ok else 1


def cmd_pack(a) -> int:
    from . import pack as PK

    scene, _ = _load(a.scene)
    text = Path(a.scene).read_text(encoding="utf-8")
    for p in PK.pack(scene, text, a.out_dir, a.only, a.labels, a.width, a.guide_style):
        print(f"gravado: {p}")
    return 0


def cmd_unpack(a) -> int:
    from . import pack as PK

    meta = PK.unpack(a.image)
    if not meta:
        print("a imagem não traz metadados do scenelang", file=sys.stderr)
        return 1
    if a.what == "all":
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(meta.get(f"scenelang-{a.what}", ""))
    return 0


def cmd_cutout(a) -> int:
    from PIL import Image

    from . import verify as ver

    if a.black and a.white:
        out = ver.cutout_difference(Image.open(a.black), Image.open(a.white))
    elif a.image:
        scene, _ = _load(a.scene)
        out = ver.cutout_chroma(scene, Image.open(a.image))
    else:
        print("informe a imagem sobre a chave, ou --black e --white (alpha: difference)", file=sys.stderr)
        return 2
    out.save(a.out)
    print(f"gravado: {a.out}")
    return 0


def cmd_sweep(a) -> int:
    import re

    import yaml

    from . import variants as var

    scene, _ = _load(a.scene)
    try:
        path, items = var.make_sweep(scene.data, a.axis)
    except var.VariantError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    made, skipped = [], 0
    for i, (label, data) in enumerate(items, 1):
        text = dump_scene(data)
        diags, sc, _ = load_text(text)
        if sc is None:
            skipped += 1
            print(f"variante {label!r} inválida:", file=sys.stderr)
            for d in diags:
                print(f"  {d}", file=sys.stderr)
            continue
        slug = re.sub(r"[^\w.-]+", "_", label)
        (out / f"{i}_{slug}.yaml").write_text(text, encoding="utf-8")
        body = to_regions(sc) if a.target == "regions" else BACKENDS[a.target](sc)
        (out / f"{i}_{slug}.{'json' if a.target != 'prose' else 'txt'}").write_text(body, encoding="utf-8")
        made.append({"n": i, "valor": label})
    form = {"eixo": path, "valores_na_ordem": [m["valor"] for m in made], "variantes": made,
            "pergunta": f"Ponha as imagens em ordem, da que tem MENOS para a que tem MAIS de '{path}' (use os números n).",
            "ordem_observada": None}
    (out / "ficha_eixo.yaml").write_text(yaml.safe_dump(form, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"{len(made)} variante(s) em {out}" + (f"; {skipped} inválida(s) pulada(s)" if skipped else ""))
    return 0 if made else 1


def cmd_sweep_score(a) -> int:
    import yaml

    from . import variants as var

    form = yaml.safe_load(Path(a.form).read_text(encoding="utf-8"))
    obs = form.get("ordem_observada")
    exp = [m["n"] for m in form["variantes"]]
    if not obs or sorted(obs) != sorted(exp):
        print(f"preencha ordem_observada com todos os números {exp}, do menor para o maior", file=sys.stderr)
        return 2
    tau = var.kendall_tau(exp, obs)
    verdict = "controle monotônico (a imagem mudou na ordem pedida)" if tau == 1 else (
        "controle parcial" if tau > 0 else "sem controle visível neste eixo")
    print(f"tau de Kendall = {tau:+.2f}: {verdict}")
    return 0 if tau == 1 else 1


def cmd_snap(a) -> int:
    from PIL import Image

    from . import verify as ver

    scene, _ = _load(a.scene)
    try:
        out = ver.snap(scene, Image.open(a.image), a.grid, a.colors, a.to_palette, a.fit, a.scale)
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    out.save(a.out)
    print(f"gravado: {a.out}")
    return 0


def cmd_sheet_prompt(a) -> int:
    scene, _ = _load(a.scene)
    from . import variants as var

    path, items = var.make_sweep(scene.data, a.axis)
    labels = [lb for lb, _ in items]
    first = load_text(dump_scene(items[0][1]))[1]
    body = BACKENDS["prose"](first)
    lines = [f"{i}: {path} = {lb}" for i, lb in enumerate(labels, 1)]
    sheet = (f"FOLHA DE VARIANTES: desenhe {len(labels)} versões do mesmo personagem lado a lado, da esquerda para a direita, "
             "em um único quadro, com o mesmo tamanho, pose e enquadramento; muda APENAS o eixo abaixo, de forma bem visível, "
             "e nada mais. Numere as versões 1 a " + str(len(labels)) + " de baixo, sem outro texto.\n" + "\n".join(lines) + "\n\n")
    text = sheet + body
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"gravado: {a.out}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_sheet_measure(a) -> int:
    from PIL import Image

    from . import variants as var
    from . import verify as ver

    scene, _ = _load(a.scene)
    rows = ver.sheet_metrics(scene, Image.open(a.image), a.n)
    keys = ["area", "largura", "irregularidade"]
    print("n  " + "  ".join(f"{k:>14}" for k in keys))
    for r in rows:
        print(f"{r['n']}  " + "  ".join(f"{r[k]:>14}" for k in keys))
    if a.metric:
        vals = [r[a.metric] for r in rows]
        order = sorted(range(len(vals)), key=lambda i: vals[i], reverse=a.decreasing)
        tau = var.kendall_tau(list(range(1, a.n + 1)), [i + 1 for i in order])
        print(f"\nmétrica {a.metric}: tau de Kendall vs. ordem pedida = {tau:+.2f}")
        return 0 if tau == 1 else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scenelang", description="Linguagem de cena para modelos de imagem")
    p.add_argument("--version", action="version", version=f"scenelang {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="valida esquema, vocabulário, referências e conflitos")
    s.add_argument("scene"); s.add_argument("--json", action="store_true", help="diagnósticos em JSON")
    s.add_argument("--fix", action="store_true", help="aplica as correções seguras (typos de vocabulário e de campo)")
    s.add_argument("--out", help="com --fix: grava o resultado aqui em vez de sobrescrever a cena")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("primer", help="cartilha de uma página para o modelo escrever cenas")
    s.set_defaults(fn=cmd_primer)

    s = sub.add_parser("vocab", help="vocabulários fechados")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_vocab)

    s = sub.add_parser("new", help="cena inicial pronta (sem argumento: lista os modelos)")
    s.add_argument("template", nargs="?"); s.add_argument("--out"); s.set_defaults(fn=cmd_new)

    s = sub.add_parser("compile", help="compila a cena para um backend")
    s.add_argument("scene"); s.add_argument("--target", choices=sorted(BACKENDS), default="prose")
    s.add_argument("--size", help="tamanho em px para o backend regions, ex.: 1344x756")
    s.add_argument("--pass", dest="passname", choices=["black", "white"], help="passada do alpha: difference")
    s.add_argument("--loss", action="store_true", help="lista o que a cena declara e o backend não leva ao gerador")
    s.add_argument("--strict", action="store_true", help="falha (código 3) se houver perda real ou a cena não tiver asserts")
    s.add_argument("--out"); s.set_defaults(fn=cmd_compile)

    s = sub.add_parser("pose", help="folha de construção da pose (caixas, cilindros, esferas) em 3 vistas")
    s.add_argument("scene"); s.add_argument("entity"); s.add_argument("--out", required=True)
    s.add_argument("--style", choices=["mannequin", "construction"], default="mannequin",
                   help="mannequin: figura limpa de referência (padrão); construction: folha didática em 3 vistas, com caixas e cilindros")
    s.set_defaults(fn=cmd_pose)

    s = sub.add_parser("correct", help="mede a imagem, grava o relatório e prepara o prompt da próxima rodada")
    s.add_argument("scene"); s.add_argument("image")
    s.add_argument("--boxes", help="JSON {id: [x,y,w,h]} de quem olhou a imagem")
    s.add_argument("--out-dir", default="rodada")
    s.set_defaults(fn=cmd_correct)

    s = sub.add_parser("pack", help="junta prompt, guia de composição e cena em um formato que o modelo de destino aceita")
    s.add_argument("scene"); s.add_argument("--out-dir", required=True)
    s.add_argument("--only", choices=["text", "guide", "single"], help="text: só prompt.txt; guide: guia.png + prompt; single: UM arquivo (guia + prompt na imagem)")
    s.add_argument("--labels", action=argparse.BooleanOptionalAction, default=None,
                   help="escreve o nome de cada elemento no guia (padrão: sim em --only single, não nos demais)")
    s.add_argument("--width", type=int, default=1024)
    s.add_argument("--guide-style", choices=["blocks", "seg"], default="blocks",
                   help="blocks: retângulos com borda; seg: mapa de segmentação (áreas chapadas, sem borda), para geradores com controle de estrutura")
    s.set_defaults(fn=cmd_pack)

    s = sub.add_parser("unpack", help="lê prompt/cena embutidos nos metadados de um PNG gerado por `pack`")
    s.add_argument("image"); s.add_argument("what", nargs="?", default="all", choices=["all", "prompt", "yaml", "cena"])
    s.set_defaults(fn=cmd_unpack)

    s = sub.add_parser("locate", help="mede onde as entidades ficaram na imagem e detecta espelhamento")
    s.add_argument("scene"); s.add_argument("image", nargs="?")
    s.add_argument("--boxes", help="JSON {id: [x,y,w,h]} de quem olhou a imagem")
    s.add_argument("--form", action="store_true", help="gera o pedido para um modelo de visão devolver as caixas")
    s.set_defaults(fn=cmd_locate)

    s = sub.add_parser("check", help="roda os asserts sobre o layout (sem imagem)")
    s.add_argument("scene"); s.set_defaults(fn=cmd_check)

    s = sub.add_parser("render", help="desenha o esquema 2D (SVG ou PNG)")
    s.add_argument("scene"); s.add_argument("--out", required=True); s.add_argument("--width", type=int, default=960)
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("eval-form", help="gera a ficha de avaliação da imagem")
    s.add_argument("scene"); s.add_argument("--round", type=int, default=1); s.add_argument("--out")
    s.set_defaults(fn=cmd_eval_form)

    s = sub.add_parser("eval-apply", help="aplica a ficha preenchida e reforça o que falhou")
    s.add_argument("scene"); s.add_argument("answers"); s.add_argument("--out")
    s.add_argument("--lock-passed", action="store_true", help="trava (lock) as entidades dos itens aprovados")
    s.set_defaults(fn=cmd_eval_apply)

    s = sub.add_parser("plan", help="pedido estruturado para o modelo propor cores e linhas-guia")
    s.add_argument("scene"); s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("plan-apply", help="grava a proposta do modelo na cena e valida")
    s.add_argument("scene"); s.add_argument("proposal"); s.add_argument("--out"); s.set_defaults(fn=cmd_plan_apply)

    s = sub.add_parser("verify", help="mede a imagem gerada com os verificadores da cena")
    s.add_argument("scene"); s.add_argument("image"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("cutout", help="recorta o fundo e grava PNG com alfa")
    s.add_argument("scene", nargs="?"); s.add_argument("image", nargs="?")
    s.add_argument("--black"); s.add_argument("--white"); s.add_argument("--out", required=True); s.set_defaults(fn=cmd_cutout)

    s = sub.add_parser("sweep", help="gera variantes da cena variando um eixo (caminho=v1,v2,v3)")
    s.add_argument("scene"); s.add_argument("--axis", required=True); s.add_argument("--out", required=True)
    s.add_argument("--target", choices=sorted(BACKENDS), default="prose"); s.set_defaults(fn=cmd_sweep)

    s = sub.add_parser("sweep-score", help="mede se a imagem seguiu o eixo (ordem observada × esperada)")
    s.add_argument("form"); s.set_defaults(fn=cmd_sweep_score)

    s = sub.add_parser("snap", help="transforma a saída do modelo em pixel art de verdade (grade, cores, fundo transparente)")
    s.add_argument("scene"); s.add_argument("image"); s.add_argument("--out", required=True)
    s.add_argument("--grid", type=int); s.add_argument("--colors", type=int)
    s.add_argument("--to-palette", action="store_true", help="usa só as cores exatas da paleta")
    s.add_argument("--fit", action="store_true", help="recorta e encaixa o sujeito nas linhas-guia")
    s.add_argument("--scale", type=int, default=8); s.set_defaults(fn=cmd_snap)

    s = sub.add_parser("sheet-prompt", help="um prompt único com N variantes lado a lado (folha de variantes)")
    s.add_argument("scene"); s.add_argument("--axis", required=True); s.add_argument("--out"); s.set_defaults(fn=cmd_sheet_prompt)

    s = sub.add_parser("sheet-measure", help="mede cada coluna de uma folha de variantes")
    s.add_argument("scene"); s.add_argument("image"); s.add_argument("--n", type=int, default=3)
    s.add_argument("--metric", choices=["area", "largura", "irregularidade"])
    s.add_argument("--decreasing", action="store_true"); s.set_defaults(fn=cmd_sheet_measure)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
