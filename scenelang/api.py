"""Funções JSON-serializáveis para uso por modelos (ferramenta/MCP) sem tocar na linha de comando."""
from __future__ import annotations

import yaml

from . import compile as CP
from . import fixes, normalize, plan as PL, primer as PR, templates
from .validate import load_text


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
