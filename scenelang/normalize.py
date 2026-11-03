"""Padrões e apelidos: o que um modelo pode escrever de forma curta sem errar.

Aplicado só em `load_text` (antes da validação), nunca dentro de `validate_data`.
Cada alteração vira uma nota legível; nada é silencioso no resultado da API.
"""
from __future__ import annotations

import copy
import unicodedata

ALIASES = {
    "kind": {"personagem": "character", "criatura": "creature", "monstro": "creature", "objeto": "prop", "item": "prop",
             "estrutura": "structure", "construcao": "structure", "terreno": "terrain", "ceu": "sky", "efeito": "effect",
             "fonte_de_luz": "light_source", "luz": "light_source", "veiculo": "vehicle"},
    "plane": {"fundo": "background", "ao_fundo": "background", "plano_medio": "midground", "meio": "midground",
              "primeiro_plano": "foreground", "frente": "foreground"},
    "orient": {"cima": "up", "baixo": "down", "esquerda": "left", "direita": "right", "cima_esquerda": "up_left",
               "cima_direita": "up_right", "baixo_esquerda": "down_left", "baixo_direita": "down_right",
               "para_a_camera": "toward_camera", "para_camera": "toward_camera", "afastando": "away"},
    "bg_mode": {"chroma_key": "chromakey", "chroma": "chromakey", "green_screen": "chromakey", "greenscreen": "chromakey",
                "fundo_da_cena": "scene", "cena": "scene"},
    "strength": {"strong": "high", "weak": "low", "light": "low", "medium": "normal", "none": "calm", "gale": "max",
                 "forte": "high", "fraco": "low", "moderado": "normal", "calmo": "calm", "vendaval": "max"},
    "grid": {"ouro": "golden", "dourada": "golden", "aurea": "golden", "tercos": "thirds", "terco": "thirds"},
}


def _key(v: str) -> str:
    t = unicodedata.normalize("NFD", v.strip().lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return t.replace(" ", "_").replace("-", "_")


def _alias(table: str, v):
    if isinstance(v, str):
        return ALIASES[table].get(_key(v))
    return None


def _fix_spec_sheen(spec, notes, where):
    from .materials import SHEEN_ALIASES

    if not isinstance(spec, dict):
        return
    for holder in (spec, spec.get("scales") if isinstance(spec.get("scales"), dict) else None):
        if holder is not None and isinstance(holder.get("sheen"), str) and _key(holder["sheen"]) in SHEEN_ALIASES:
            new = SHEEN_ALIASES[_key(holder["sheen"])]
            notes.append(f"{where}.sheen {holder['sheen']!r} → {new!r}")
            holder["sheen"] = new


def _fix_sheens(e, notes, where):
    _fix_spec_sheen(e.get("material"), notes, f"{where}.material")
    if isinstance(e.get("parts"), dict):
        for part, spec in e["parts"].items():
            _fix_spec_sheen(spec, notes, f"{where}.parts.{part}")


def apply_defaults(data):
    """Devolve (cópia ajustada, notas). Dados que não são mapa passam intactos."""
    if not isinstance(data, dict):
        return data, []
    d = copy.deepcopy(data)
    notes: list[str] = []
    if "version" not in d:
        d["version"] = 1
    g = d.get("grid")
    if g is None:
        d["grid"] = {"kind": "golden"}
        notes.append("grid ausente → {kind: golden}")
    elif isinstance(g, str):
        d["grid"] = {"kind": _alias("grid", g) or g}
        notes.append(f"grid: {g!r} → mapa com kind")
    elif isinstance(g, dict) and _alias("grid", g.get("kind")):
        notes.append(f"grid.kind {g['kind']!r} → {_alias('grid', g['kind'])!r}")
        g["kind"] = _alias("grid", g["kind"])
    if isinstance(d.get("style"), str):
        notes.append("style em texto → {base: texto}")
        d["style"] = {"base": d["style"]}
    cv = d.get("canvas")
    if isinstance(cv, str):
        d["canvas"] = {"shape": "rect", "ratio": cv}
        notes.append(f"canvas: {cv!r} → {{shape: rect, ratio: {cv!r}}}")
    elif isinstance(cv, dict) and "ratio" in cv and isinstance(cv["ratio"], str) and "x" in cv["ratio"].lower() and ":" not in cv["ratio"]:
        a, _, b = cv["ratio"].lower().partition("x")
        if a.strip().isdigit() and b.strip().isdigit():
            notes.append(f"ratio {cv['ratio']!r} → '{a.strip()}:{b.strip()}'")
            cv["ratio"] = f"{a.strip()}:{b.strip()}"
    if isinstance(cv, dict) and "pixel_grid" in cv:
        pg = cv["pixel_grid"]
        if isinstance(pg, str):
            a, sep, b = pg.lower().replace("×", "x").partition("x")
            if a.strip().isdigit() and (not sep or a.strip() == b.strip()):
                notes.append(f"canvas.pixel_grid {pg!r} → {int(a)}")
                cv["pixel_grid"] = int(a)
    bg = d.get("background")
    if isinstance(bg, dict) and _alias("bg_mode", bg.get("mode")):
        notes.append(f"background.mode {bg['mode']!r} → {_alias('bg_mode', bg['mode'])!r}")
        bg["mode"] = _alias("bg_mode", bg["mode"])
    at = d.get("atmosphere")
    if isinstance(at, dict):
        if isinstance(at.get("mood"), str):
            notes.append(f"atmosphere.mood {at['mood']!r} → {{name: {at['mood']}}}")
            at["mood"] = {"name": at["mood"]}
        wd = at.get("wind")
        if isinstance(wd, dict) and _alias("strength", wd.get("strength")):
            notes.append(f"wind.strength {wd['strength']!r} → {_alias('strength', wd['strength'])!r}")
            wd["strength"] = _alias("strength", wd["strength"])
    vf = d.get("verify")
    if isinstance(vf, list):
        for i, v in enumerate(vf):
            if isinstance(v, str) and v.strip().isidentifier():
                notes.append(f"verify[{i}]: {v!r} → '{v.strip()}()'")
                vf[i] = v.strip() + "()"
    if isinstance(d.get("materials"), dict):
        for name, spec in d["materials"].items():
            _fix_spec_sheen(spec, notes, f"materials.{name}")
    ents = d.get("entities")
    if isinstance(ents, list):
        for i, e in enumerate(ents):
            if not isinstance(e, dict):
                continue
            for field in ("kind", "plane", "orient"):
                new = _alias(field, e.get(field))
                if new:
                    notes.append(f"entities[{i}].{field}: {e[field]!r} → {new!r}")
                    e[field] = new
            from .character import CHAR_KEYS

            loose = [k for k in CHAR_KEYS if k in e]
            if loose:
                ch = e.setdefault("character", {}) if isinstance(e.get("character", {}), dict) else None
                if ch is not None:
                    for k in loose:
                        ch.setdefault(k, e.pop(k))
                    notes.append(f"entities[{i}]: {', '.join(loose)} → dentro de character")
            _fix_sheens(e, notes, f"entities[{i}]")
            if "label" not in e and isinstance(e.get("id"), str):
                e["label"] = e["id"].replace("_", " ")
                notes.append(f"entities[{i}].label ausente → {e['label']!r} (do id)")
    return d, notes
