"""Funções JSON-serializáveis para uso por modelos (ferramenta/MCP) sem tocar na linha de comando."""
from __future__ import annotations

import yaml

from . import compile as CP
from . import fixes, normalize, plan as PL, primer as PR, templates
from .validate import load_text


def plain(o):   # json.dumps(default=plain): numpy (bool_/float64/int64) e afins viram tipos JSON
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "tolist"):
        return o.tolist()
    return str(o)


def _result(diags, scene, notes) -> dict:
    errs = [d.to_dict() for d in diags if d.level == "error"]
    return {"ok": scene is not None and not errs, "errors": errs,
            "warnings": [d.to_dict() for d in diags if d.level == "warning"], "defaults_applied": notes}


def validate(text: str) -> dict:
    diags, scene, data = load_text(text)
    try:
        _, notes = normalize.apply_defaults(yaml.safe_load(text))
    except yaml.YAMLError:
        notes = []
    return _result(diags, scene, notes)


def fix(text: str) -> dict:
    """Aplica as correções seguras e devolve o novo texto YAML + o que mudou + o que sobrou."""
    diags, _scene, data = load_text(text)
    if data is None:
        return {"ok": False, "text": text, "applied": [], **_result(diags, None, [])}
    new, applied = fixes.apply_fixes(data, diags)
    out = yaml.safe_dump(new, allow_unicode=True, sort_keys=False)
    diags2, scene2, _ = load_text(out)
    return {"text": out, "applied": applied, **_result(diags2, scene2, [])}


def compile_scene(text: str, target: str = "prose", size: str | None = None) -> dict:
    diags, scene, _ = load_text(text)
    if scene is None:
        return {"ok": False, "errors": [d.to_dict() for d in diags if d.level == "error"]}
    if target not in CP.BACKENDS:
        return {"ok": False, "errors": [{"message": f"target desconhecido: {target}", "accepted": sorted(CP.BACKENDS)}]}
    out = CP.to_regions(scene, size) if target == "regions" else CP.BACKENDS[target](scene)
    return {"ok": True, "target": target, "output": out, "warnings": [d.to_dict() for d in diags if d.level == "warning"]}


def plan(text: str) -> dict:
    diags, scene, _ = load_text(text)
    if scene is None:
        return {"ok": False, "errors": [d.to_dict() for d in diags if d.level == "error"]}
    from . import palette as PAL

    return {"ok": True, "plan": PL.plan_request(scene), "palette_request": PAL.plan_request(scene.data)}


def primer() -> str:
    return PR.primer()


def vocab() -> dict:
    return PR.vocab()


def new(template: str) -> str:
    return templates.get(template)


# --- ferramentas com arquivos/imagens (usadas pelo servidor MCP) -------------------------------------------------

def _scene(text: str):
    diags, scene, _ = load_text(text)
    errs = [d.to_dict() for d in diags if d.level == "error"]
    return scene, ({"ok": False, "errors": errs} if scene is None else None)


def loss_report(text: str, target: str = "prose") -> dict:
    from . import loss as LS

    scene, err = _scene(text)
    if err:
        return err
    items = LS.report(scene, target)
    return {"ok": True, "target": target, "items": [str(i) for i in items if i.level not in ("preserved", "meta")],
            "fidelity": LS.fidelity(items), "summary": LS.summary(items), "blocking": bool(LS.blocking(items))}


def check_layout(text: str) -> dict:
    from .assertions import evaluate_all

    scene, err = _scene(text)
    if err:
        return err
    res = evaluate_all(scene)
    return {"ok": all(r.ok for r in res), "asserts": [{"assert": r.raw, "ok": r.ok, "detail": r.detail} for r in res]}


def render_schema(text: str, out_dir: str, width: int = 960) -> dict:
    from .render import write_render

    scene, err = _scene(text)
    if err:
        return err
    return {"ok": True, "files": [str(p) for p in write_render(scene, out_dir, width)]}


def pack_files(text: str, out_dir: str, only: str | None = None, guide_style: str = "blocks", width: int = 1024) -> dict:
    from . import pack as PK

    scene, err = _scene(text)
    if err:
        return err
    try:
        res = PK.pack_result(scene, text, out_dir, only, None, width, guide_style)
    except PK.PackError as e:
        return {"ok": False, "errors": [{"message": str(e)}]}
    prompt = next((p.read_text(encoding="utf-8") for p in res["files"] if p.name == "prompt.txt"), None)
    return {"ok": True, "files": [str(p) for p in res["files"]], "prompt": prompt, "warnings": res["warnings"],
            "legend": [{"id": r["id"], "color": r.get("cor")} for r in res["manifest"]["guia"]["entidades"] if r.get("cor")]}


def pose_sheet(text: str, entity: str, out_path: str, style: str = "mannequin") -> dict:
    from . import render as R, skeleton

    scene, err = _scene(text)
    if err:
        return err
    raw = next((e for e in scene.data["entities"] if e.get("id") == entity), None)
    if raw is None or not isinstance(raw.get("pose"), dict):
        return {"ok": False, "errors": [{"message": f"a entidade {entity!r} não existe ou não tem `pose`"}]}
    svg = skeleton.sheet_svg(raw["pose"], entity) if style == "construction" else skeleton.reference_svg(raw["pose"])
    return {"ok": True, "files": [str(p) for p in R.write_svg_text(svg, out_path)]}


def correct_round(text: str, image_path: str, out_dir: str, boxes: dict | None = None) -> dict:
    """Mede a imagem e devolve achados, a cena corrigida e o prompt da próxima rodada (grava relatorio.json etc.)."""
    import json
    from pathlib import Path

    from PIL import Image

    from . import correct as CR
    from .compile import to_prose
    from .evalform import dump_scene

    scene, err = _scene(text)
    if err:
        return err
    m = CR.measure_full(scene, Image.open(image_path), boxes)
    findings, items = m.findings, m.items
    if not findings:
        return {"ok": False, "errors": [{"message": "nada a medir: declare `verify`, `signature` nas entidades ou informe `boxes`"}]}
    new, pl = CR.next_scene_plan(scene, findings, items, Path(image_path).name)
    corr = pl.texts()
    new_text = dump_scene(new)
    diags, ok_scene, _ = load_text(new_text)
    if ok_scene is None:
        return {"ok": False, "errors": [d.to_dict() for d in diags if d.level == "error"]}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rel = CR.report(scene, findings, items, Path(image_path).name, pl, m.located, m.skipped_asserts)
    (out / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2, default=plain), encoding="utf-8")
    (out / "cena.next.yaml").write_text(new_text, encoding="utf-8")
    prompt_next = to_prose(ok_scene)
    (out / "prompt_next.txt").write_text(prompt_next, encoding="utf-8")
    return {"ok": True, "all_met": all(f.ok for f in findings),
            "findings": [{"kind": f.kind, "check": f.check, "ok": f.ok, "detail": f.detail} for f in findings],
            "corrections": corr, "deferred": [vars(x) for x in pl.deferred], "unresolved": [vars(x) for x in pl.unresolved], "next_scene": new_text, "prompt_next": prompt_next, "files": [str(out / n) for n in ("relatorio.json", "cena.next.yaml", "prompt_next.txt")]}


def locate_image(text: str, image_path: str, boxes: dict | None = None) -> dict:
    from PIL import Image

    from . import locate as LC

    scene, err = _scene(text)
    if err:
        return err
    located = LC.locate_detailed(scene, Image.open(image_path), boxes)
    items = LC.usable(located)
    rows = [{"id": i.id, "status": i.status, "source": i.source, "confidence": i.confidence, "reason": i.reason, "declared": list(i.declared),
             "measured": list(i.measured) if i.measured else None, "iou": LC.iou(i.declared, i.measured) if i.measured else None} for i in located]
    if not items:
        return {"ok": False, "entities": rows, "errors": [{"message": "nenhuma entidade localizada com segurança: declare `signature` ou informe `boxes` [x,y,w,h] normalizadas"}]}
    verdict, detail = LC.mirror_verdict(items)
    res, skipped = LC.recheck_asserts(scene, {i.id: i.measured for i in items})
    return {"ok": verdict != "espelhada" and all(r.ok for r in res), "mirror": verdict, "mirror_detail": detail, "entities": rows,
            "asserts": [{"assert": r.raw, "ok": r.ok, "detail": r.detail} for r in res], "skipped_asserts": skipped}


def locate_form(text: str) -> dict:
    from . import locate as LC

    scene, err = _scene(text)
    return err or {"ok": True, "form": LC.form(scene)}


def verify_image(text: str, image_path: str) -> dict:
    from PIL import Image

    from . import verify as ver

    scene, err = _scene(text)
    if err:
        return err
    res = ver.run(scene, Image.open(image_path))
    return {"ok": all(r.ok for r in res), "results": [{"verify": r.raw, "ok": r.ok, "detail": r.detail, "score": r.score} for r in res]}
