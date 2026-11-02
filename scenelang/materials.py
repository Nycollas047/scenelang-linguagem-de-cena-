"""Materiais, texturas e orçamento de detalhe.

materials:                        # biblioteca da cena (reutilizável via import)
  bronze_gasto: {base: metal, finish: scratched, wear: high, detail_scale: fine,
                 pattern: "filigrana gravada", sheen: normal, color: "@bronze"}
entidade:
  material: bronze_gasto          # ou um mapa inline
  parts: {armor: bronze_gasto, cape: {base: cloth, finish: matte}}
  detail: high                    # orçamento de detalhe da entidade
detail:                           # orçamento por zona (no máximo UM "max" na cena inteira)
  focal: max
  foreground: high
  midground: normal
  background: low
"""
from __future__ import annotations

from . import color as C
from . import palette as PAL
from . import vocab as V
from .checks import enum_check, unknown_keys

BASES = {"metal": "metal", "stone": "pedra", "cloth": "tecido", "leather": "couro", "skin": "pele", "wood": "madeira",
         "glass": "vidro", "water": "água", "crystal": "cristal", "fur": "pelo", "paper": "papel", "bone": "osso"}
FINISHES = {"polished": "polido", "matte": "fosco", "scratched": "arranhado", "oxidized": "oxidado", "wet": "molhado",
            "rough": "áspero", "glossy": "lustroso", "mossy": "coberto de musgo", "dusty": "empoeirado"}
WEARS = {"low": "quase novo", "normal": "com desgaste de uso", "high": "muito desgastado"}
SCALES = {"fine": "grão fino", "medium": "grão médio", "coarse": "grão grosso"}
SHEENS = {"low": "brilho discreto", "normal": "brilho médio", "high": "brilho forte", "max": "brilho intenso"}
MAT_KEYS = {"base", "finish", "wear", "detail_scale", "pattern", "sheen", "color"}
ZONES = ("focal", "foreground", "midground", "background")
DETAIL_PT = {"max": "textura e detalhe máximos", "high": "muito detalhado", "normal": "detalhe moderado", "low": "simplificado e suave"}
ZONE_PT = {"focal": "no ponto focal", "foreground": "no primeiro plano", "midground": "no plano médio", "background": "no fundo"}


def _check_spec(c, path: str, spec, data: dict) -> None:
    if not isinstance(spec, dict):
        c.error(path, "deve ser um mapa de material", got=spec)
        return
    unknown_keys(c, path, spec, MAT_KEYS)
    enum_check(c, f"{path}.base", spec.get("base"), list(BASES))
    if "finish" in spec:
        enum_check(c, f"{path}.finish", spec["finish"], list(FINISHES))
    if "wear" in spec:
        enum_check(c, f"{path}.wear", spec["wear"], list(WEARS))
    if "detail_scale" in spec:
        enum_check(c, f"{path}.detail_scale", spec["detail_scale"], list(SCALES))
    if "sheen" in spec:
        enum_check(c, f"{path}.sheen", spec["sheen"], list(SHEENS))
    if "pattern" in spec and not isinstance(spec["pattern"], str):
        c.error(f"{path}.pattern", "deve ser um texto", got=spec["pattern"])
    if "color" in spec:
        try:
            PAL.resolve_spec(data, spec["color"])
        except C.ColorError as e:
            c.error(f"{path}.color", str(e), got=spec["color"])
    if spec.get("finish") == "polished" and spec.get("wear") == "high":
        c.warn(path, "acabamento polido com desgaste alto é contraditório", hint="use finish: scratched ou wear: normal")
    if spec.get("finish") in ("polished", "glossy") and spec.get("sheen") == "low":
        c.warn(path, "acabamento brilhante com brilho discreto é contraditório", hint="suba o sheen ou use finish: matte")
    if spec.get("finish") == "matte" and spec.get("sheen") in ("high", "max"):
        c.warn(path, "acabamento fosco com brilho forte é contraditório", hint="baixe o sheen ou use finish: glossy")


def _resolve(data: dict, ref):
    if isinstance(ref, str):
        return (data.get("materials") or {}).get(ref)
    return ref if isinstance(ref, dict) else None


def check(c, data: dict) -> None:
    mats = data.get("materials")
    if mats is not None:
        if not isinstance(mats, dict):
            c.error("$.materials", "deve ser um mapa nome → material", got=mats)
        else:
            for name, spec in mats.items():
                _check_spec(c, f"$.materials.{name}", spec, data)
    maxes = []
    det = data.get("detail")
    if det is not None:
        if not isinstance(det, dict):
            c.error("$.detail", "deve ser um mapa zona → nível", got=det)
        else:
            unknown_keys(c, "$.detail", det, ZONES)
            for z, lv in det.items():
                if z in ZONES and enum_check(c, f"$.detail.{z}", lv, V.LEVELS) and lv == "max":
                    maxes.append(f"detail.{z}")
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict):
            continue
        p = f"$.entities[{i}]"
        refs = {}
        if "material" in e:
            refs["material"] = e["material"]
        if "parts" in e:
            if not isinstance(e["parts"], dict):
                c.error(f"{p}.parts", "deve ser um mapa parte → material", got=e["parts"])
            else:
                for part, ref in e["parts"].items():
                    refs[f"parts.{part}"] = ref
        for key, ref in refs.items():
            if isinstance(ref, str):
                if ref not in (data.get("materials") or {}):
                    c.error(f"{p}.{key}", "material inexistente", got=ref, accepted=sorted(data.get("materials") or {}))
            else:
                _check_spec(c, f"{p}.{key}", ref, data)
        if "detail" in e:
            if enum_check(c, f"{p}.detail", e["detail"], V.LEVELS) and e["detail"] == "max":
                maxes.append(f"entities.{e.get('id', i)}.detail")
    if len(maxes) > 1:
        c.error("$.detail", "detalhe máximo duplo: só um ponto da cena pode concentrar o detalhe máximo", got=maxes,
                hint="deixe um 'max' e rebaixe os demais para high")


def describe(spec: dict, data: dict) -> str:
    bits = []
    base = BASES[spec["base"]]
    fin = FINISHES.get(spec.get("finish", ""), "")
    bits.append(f"{base} {fin}".strip())
    if "wear" in spec:
        bits.append(WEARS[spec["wear"]])
    if "detail_scale" in spec:
        bits.append(SCALES[spec["detail_scale"]])
    if "sheen" in spec:
        bits.append(SHEENS[spec["sheen"]])
    if spec.get("pattern"):
        bits.append(spec["pattern"])
    if "color" in spec:
        try:
            bits.append("cor " + C.describe(PAL.resolve_spec(data, spec["color"])))
        except C.ColorError:
            pass
    return ", ".join(bits)


def entity_sentence(scene, entity_id: str) -> str | None:
    raw = next((e for e in scene.data["entities"] if e["id"] == entity_id), {})
    parts = []
    if "material" in raw:
        spec = _resolve(scene.data, raw["material"])
        if spec:
            parts.append(f"Material: {describe(spec, scene.data)}.")
    if isinstance(raw.get("parts"), dict):
        items = []
        for part, ref in raw["parts"].items():
            spec = _resolve(scene.data, ref)
            if spec:
                items.append(f"{V.part_pt(part)}: {describe(spec, scene.data)}")
        if items:
            parts.append("Materiais por parte — " + "; ".join(items) + ".")
    if raw.get("detail"):
        parts.append(f"Nível de detalhe: {DETAIL_PT[raw['detail']]}.")
    return " ".join(parts) or None


def detail_section(scene) -> str | None:
    det = scene.data.get("detail")
    if not isinstance(det, dict) or not det:
        return None
    return "Distribuição de detalhe: " + "; ".join(f"{DETAIL_PT[v]} {ZONE_PT[z]}" for z, v in det.items() if z in ZONE_PT) + "."
