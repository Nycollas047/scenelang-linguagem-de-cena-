"""Linha de comando:  python -m scenelang <comando> cena.yaml [opções]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .assertions import evaluate_all
from .compile import BACKENDS, to_regions
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


def cmd_compile(a) -> int:
    scene, _ = _load(a.scene)
    if a.target == "regions":
        out = to_regions(scene, a.size)
    else:
        out = BACKENDS[a.target](scene)
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
    new, failed = apply_answers(scene, Path(a.answers).read_text(encoding="utf-8"))
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scenelang", description="Linguagem de cena para modelos de imagem")
    p.add_argument("--version", action="version", version=f"scenelang {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="valida esquema, vocabulário, referências e conflitos")
    s.add_argument("scene"); s.add_argument("--json", action="store_true", help="diagnósticos em JSON")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("compile", help="compila a cena para um backend")
    s.add_argument("scene"); s.add_argument("--target", choices=sorted(BACKENDS), default="prose")
    s.add_argument("--size", help="tamanho em px para o backend regions, ex.: 1344x756")
    s.add_argument("--out"); s.set_defaults(fn=cmd_compile)

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
    s.set_defaults(fn=cmd_eval_apply)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
